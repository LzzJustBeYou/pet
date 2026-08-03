import ctypes
import ctypes.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QPoint, QSettings, QSize, Qt, QTimer, qInstallMessageHandler
from PyQt5.QtGui import QCursor, QGuiApplication, QIcon, QMovie, QRegion
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QSlider,
    QSystemTrayIcon,
    QWidget,
    QWidgetAction,
    qApp,
)

from animation import GifVisual, SpriteAtlasPlayer, load_gif_visual
from autostart import set_autostart
from break_overlay import BreakOverlay
from health_reminder import HealthReminderController
from interaction import PetInteractionController
from pet_package import (
    PetPackage,
    PetPackageError,
    canonical_path,
    find_pet_directories,
    load_pet_package,
)
from settings_window import DEFAULT_SETTINGS, SettingsWindow
from sound import SoundManager
from holiday_calendar import HolidayCalendar
from todo_models import local_now
from todo_notifier import (
    CALENDAR_CHANGE_KIND,
    TODO_CHANGE_KIND,
    TodoChangeNotifier,
    signal_path_for_database,
)
from todo_scheduler import TodoScheduler
from todo_store import TodoStore
from todo_ui import TodoManagerWindow, TodoQuickPanel, TodoReminderBubble
from tray_controller import TrayController


_previous_qt_message_handler = None
_qt_message_filter_installed = False


def _qt_message_handler(message_type, context, message):
    if message.startswith(
        "qt.network.monitor: Could not get the INetworkConnection instance"
    ):
        return
    if _previous_qt_message_handler is not None:
        _previous_qt_message_handler(message_type, context, message)
        return
    print(message, file=sys.stderr)


def install_qt_message_filter():
    global _previous_qt_message_handler, _qt_message_filter_installed
    if not _qt_message_filter_installed:
        _previous_qt_message_handler = qInstallMessageHandler(_qt_message_handler)
        _qt_message_filter_installed = True


def configure_app(app: QApplication) -> None:
    """设置应用级参数（组织名/应用名/退出策略）。"""
    app.setOrganizationName("PetApp")
    app.setApplicationName("DesktopPet")
    # 托盘常驻应用：最后一个可见窗口关闭/隐藏时不退出进程，
    # 避免休息浮层结束后应用被自动退出。
    app.setQuitOnLastWindowClosed(False)
    if sys.platform == "win32":
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))


def pin_macos_window_level(win_id: int, target_level: int = 1000) -> bool:
    """macOS 上用 objc 把窗口层级硬拉到指定级别，返回是否成功。"""
    if QGuiApplication.platformName() == "offscreen":
        return False
    if not win_id:
        return False
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        c_void_p = ctypes.c_void_p
        c_long = ctypes.c_long
        selector = objc.sel_registerName
        selector.restype = c_void_p
        selector.argtypes = [ctypes.c_char_p]

        msg_id = ctypes.CFUNCTYPE(c_void_p, c_void_p, c_void_p)
        msg_void_long = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_long)
        msg_long = ctypes.CFUNCTYPE(c_long, c_void_p, c_void_p)

        nswindow = ctypes.cast(objc.objc_msgSend, msg_id)(
            c_void_p(win_id), selector(b"window")
        )
        if not nswindow:
            return False

        current_level = ctypes.cast(objc.objc_msgSend, msg_long)(
            nswindow, selector(b"level")
        )
        if current_level != target_level:
            ctypes.cast(objc.objc_msgSend, msg_void_long)(
                nswindow,
                selector(b"setLevel:"),
                c_long(target_level),
            )
            ctypes.cast(objc.objc_msgSend, msg_void_long)(
                nswindow,
                selector(b"setCollectionBehavior:"),
                c_long(33),
            )
        return True
    except Exception as exc:
        print(f"[DesktopPet] pin failed: {exc}", file=sys.stderr)
        return False


def resource_path(relative_path):
    """Return a resource path in development and PyInstaller builds."""
    base_path = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return os.path.join(str(base_path), relative_path)


def scan_actions(actions_dir="actions"):
    """Return GIF actions grouped by their immediate parent directory."""
    categories = []
    target_dir = resource_path(actions_dir)
    if not os.path.isdir(target_dir):
        return categories

    for category in sorted(os.listdir(target_dir)):
        category_path = os.path.join(target_dir, category)
        if not os.path.isdir(category_path):
            continue
        actions = []
        for filename in sorted(os.listdir(category_path)):
            if filename.lower().endswith(".gif"):
                actions.append(
                    (
                        os.path.splitext(filename)[0],
                        os.path.join(category_path, filename),
                    )
                )
        if actions:
            categories.append((category, actions))
    return categories


PRESET_SIZES = {
    "小（高度 80）": 80,
    "中（高度 100）": 100,
    "大（高度 150）": 150,
    "超大（高度 200）": 200,
}
MIN_SIZE = 40
MAX_SIZE = 300
DEFAULT_SIZE = 100
DEFAULT_GIF_NAME = "臭臭小八"
MIN_VISIBLE_PIXELS = 20

# 预研分支遗留的宠物开关，已按 v0.3.0-tag 行为移除；启动时自动清理，
# 避免旧构建或残留配置继续生效（如 pet/opacity=0.3 导致宠物半透明）。
OBSOLETE_SETTINGS_KEYS = ("pet/opacity", "pet/pinned", "pet/interactive")


@dataclass
class PetMenuEntry:
    package_dir: Path
    source_key: str
    origin: str
    package: Optional[PetPackage] = None
    error: Optional[str] = None
    runtime_id: str = ""
    display_name: str = ""


class DesktopPet(QWidget):
    def __init__(
        self,
        settings=None,
        todo_store: Optional[TodoStore] = None,
        holiday_calendar: Optional[HolidayCalendar] = None,
        enable_todos: bool = True,
    ):
        super().__init__()
        self.settings = settings or QSettings("PetApp", "DesktopPet")
        saved_size = self.settings.value("pet/size", DEFAULT_SIZE, type=int)
        self.pet_size = max(MIN_SIZE, min(MAX_SIZE, saved_size))

        self.movie: Optional[QMovie] = None
        self.gif_visual: Optional[GifVisual] = None
        self.current_gif: Optional[str] = None
        self.current_package_entry: Optional[PetMenuEntry] = None
        self.current_source_type: Optional[str] = None
        self.current_source_key: Optional[str] = None
        self.drag_position = QPoint()
        self._interaction_region = QRegion()
        self._base_window_region = QRegion()
        self._base_interaction_region = QRegion()
        self._pointer_inside = False
        self._position_restored = False
        self._topmost_timer: Optional[QTimer] = None
        self._todo_enabled = enable_todos
        self._todo_badge_count = 0
        self._reminders_paused = False
        self._quit_requested = False
        self.todo_store: Optional[TodoStore] = todo_store
        self.holiday_calendar: Optional[HolidayCalendar] = holiday_calendar
        self.todo_scheduler: Optional[TodoScheduler] = None
        self.todo_notifier: Optional[TodoChangeNotifier] = None
        self.todo_manager: Optional[TodoManagerWindow] = None
        self.todo_quick_panel: Optional[TodoQuickPanel] = None
        self.todo_bubble: Optional[TodoReminderBubble] = None
        self.tray: Optional[TrayController] = None
        self.settings_window: Optional[SettingsWindow] = None
        self.break_overlay: Optional[BreakOverlay] = None
        self._pressed_badge = False

        self._init_ui()
        self.health = HealthReminderController(
            self,
            work_minutes=self._setting_int("health/work_minutes"),
            break_seconds=self._setting_int("health/break_seconds"),
            long_break_every=self._setting_int("health/long_break_every"),
            long_break_minutes=self._setting_int("health/long_break_minutes"),
            enabled=self._setting_bool("health/enabled"),
        )
        self.health.break_started.connect(self._on_health_break_started)
        self.health.break_ticked.connect(self._on_health_break_ticked)
        self.health.break_finished.connect(self._on_health_break_finished)
        self.health.break_skipped.connect(self._on_health_break_skipped)
        self.break_overlay = BreakOverlay(self)
        self.break_overlay.skipped.connect(self.health.skip_break)
        self.break_overlay.hide()
        self.sound = SoundManager(
            self,
            enabled_provider=lambda: self._setting_bool("sound/enabled"),
        )
        self._restore_source()
        if self._todo_enabled:
            self._init_todos()
        self._init_tray()
        self._apply_saved_settings()

    def _init_ui(self):
        # 所有平台都声明置顶：Windows/Linux 由 Qt 维护，
        # macOS 额外用 objc 把窗口层级硬拉到 1000（kCGScreenSaverWindowLevel）。
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setMouseTracking(True)

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.label.setFixedSize(self.pet_size, self.pet_size)
        self.resize(self.pet_size, self.pet_size)

        self.todo_badge = QLabel(self)
        self.todo_badge.setAlignment(Qt.AlignCenter)
        self.todo_badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.todo_badge.hide()

        self.sprite_player = SpriteAtlasPlayer(self)
        self.sprite_player.frame_changed.connect(self.label.setPixmap)
        self.interaction = PetInteractionController(self)
        self.interaction.animation_requested.connect(self._play_sprite_animation)
        self.sprite_player.animation_finished.connect(
            self.interaction.animation_finished
        )

    def _default_gif_path(self) -> Optional[str]:
        categories = scan_actions()
        first_path = None
        for _category, actions in categories:
            for name, path in actions:
                if first_path is None:
                    first_path = path
                if name == DEFAULT_GIF_NAME:
                    return path
        return first_path

    def _restore_source(self) -> None:
        source_type = self.settings.value("pet/source_type", "", type=str)
        source_key = self.settings.value("pet/source_key", "", type=str)

        if source_type == "package" and source_key:
            entry = self._package_entry_from_key(source_key)
            if entry is not None and entry.package is not None:
                if self._load_package_entry(entry, persist=False, show_error=False):
                    return
        elif source_type == "gif" and source_key:
            gif_path = self._resolve_gif_key(source_key)
            if gif_path and os.path.isfile(gif_path):
                if self._load_gif(gif_path, persist=False, show_error=False):
                    return

        default_gif = self._default_gif_path()
        if default_gif:
            self._load_gif(default_gif, persist=True, show_error=False)

    def _play_sprite_animation(self, state: str, loop: bool) -> None:
        if self.current_source_type == "package":
            self.sprite_player.play(state, loop)

    def _configure_canvas(self, size: QSize) -> None:
        self.label.setFixedSize(size)
        self.resize(size)
        self._position_todo_badge()

    def _apply_regions(self, window_region: QRegion, interaction_region: QRegion):
        self._base_window_region = QRegion(window_region)
        self._base_interaction_region = QRegion(interaction_region)
        self._apply_effective_regions()
        QTimer.singleShot(0, self._sync_pointer_hit)

    def _apply_effective_regions(self):
        window_region = QRegion(self._base_window_region)
        interaction_region = QRegion(self._base_interaction_region)
        if hasattr(self, "todo_badge") and self.todo_badge.isVisible():
            badge_region = QRegion(self.todo_badge.geometry(), QRegion.Ellipse)
            window_region = window_region.united(badge_region)
            interaction_region = interaction_region.united(badge_region)

        if window_region.isEmpty():
            self.clearMask()
        else:
            self.setMask(window_region)
        self._interaction_region = interaction_region

    def _position_todo_badge(self):
        if not hasattr(self, "todo_badge"):
            return
        badge_size = max(18, min(28, int(min(self.width(), self.height()) * 0.26)))
        self.todo_badge.setFixedSize(badge_size, badge_size)
        # 角标贴窗口右上角（不压住宠物主体），类似 Codex 的角落角标
        self.todo_badge.move(max(0, self.width() - badge_size), 0)
        font_size = max(9, int(badge_size * 0.52))
        self.todo_badge.setStyleSheet(
            f"""
            QLabel {{
                background-color: #d93025;
                color: white;
                border: 1px solid white;
                border-radius: {badge_size // 2}px;
                font-size: {font_size}px;
                font-weight: 700;
            }}
            """
        )

    def _load_gif(self, gif_path, persist=True, show_error=True) -> bool:
        try:
            visual = load_gif_visual(str(gif_path))
            movie = QMovie(str(gif_path))
            if not movie.isValid():
                raise ValueError("GIF cannot be decoded")
        except (OSError, ValueError) as exc:
            if show_error:
                QMessageBox.warning(self, "无法加载 GIF", str(exc))
            return False

        if self.movie is not None:
            self.movie.stop()
        self.sprite_player.clear()
        self.label.clear()
        self.movie = movie
        self.gif_visual = visual
        self.current_gif = str(Path(gif_path).resolve())
        self.current_package_entry = None
        self.current_source_type = "gif"
        self.current_source_key = self._gif_key(self.current_gif)

        display_size = visual.display_size(self.pet_size)
        self._configure_canvas(display_size)
        movie.setCacheMode(QMovie.CacheAll)
        movie.setScaledSize(display_size)
        self.label.setMovie(movie)
        region = visual.mask_region(self.pet_size)
        self._apply_regions(region, region)
        self.interaction.activate(False)
        movie.start()

        if persist:
            self._persist_source()
        self._keep_current_position_visible()
        return True

    def _load_package_entry(
        self,
        entry: PetMenuEntry,
        persist=True,
        show_error=True,
    ) -> bool:
        if entry.package is None:
            if show_error:
                QMessageBox.warning(
                    self,
                    "无法加载互动宠物",
                    entry.error or "资源包无效",
                )
            return False
        try:
            self.sprite_player.load(entry.package, self.pet_size)
        except (OSError, ValueError) as exc:
            if show_error:
                QMessageBox.warning(self, "无法加载互动宠物", str(exc))
            return False

        if self.movie is not None:
            self.movie.stop()
        self.movie = None
        self.gif_visual = None
        self.current_gif = None
        self.label.clear()
        self.current_package_entry = entry
        self.current_source_type = "package"
        self.current_source_key = entry.source_key

        self._configure_canvas(self.sprite_player.display_size)
        window_region, interaction_region = self.sprite_player.mask_regions()
        self._apply_regions(window_region, interaction_region)
        self.interaction.activate(True)

        if persist:
            self._persist_source()
        self._keep_current_position_visible()
        return True

    def _persist_source(self) -> None:
        if self.current_source_type and self.current_source_key:
            self.settings.setValue("pet/source_type", self.current_source_type)
            self.settings.setValue("pet/source_key", self.current_source_key)
            self.settings.remove("pet/manual_package_dirs")

    def _gif_key(self, gif_path: str) -> str:
        resolved = Path(gif_path).resolve()
        action_root = Path(resource_path("actions")).resolve()
        try:
            relative = resolved.relative_to(action_root)
            return f"builtin-gif:{relative.as_posix()}"
        except ValueError:
            return f"external-gif:{resolved}"

    def _resolve_gif_key(self, key: str) -> Optional[str]:
        if key.startswith("builtin-gif:"):
            relative = key.split(":", 1)[1]
            return str(Path(resource_path("actions")) / Path(relative))
        if key.startswith("external-gif:"):
            return key.split(":", 1)[1]
        return key or None

    def set_pet_size(self, new_size):
        new_size = max(MIN_SIZE, min(MAX_SIZE, new_size))
        if new_size == self.pet_size:
            return
        self.pet_size = new_size

        if self.current_source_type == "package":
            self.sprite_player.set_display_height(new_size)
            self._configure_canvas(self.sprite_player.display_size)
            window_region, interaction_region = self.sprite_player.mask_regions()
            self._apply_regions(window_region, interaction_region)
        elif self.movie is not None and self.gif_visual is not None:
            display_size = self.gif_visual.display_size(new_size)
            self._configure_canvas(display_size)
            self.movie.setScaledSize(display_size)
            region = self.gif_visual.mask_region(new_size)
            self._apply_regions(region, region)

        self.settings.setValue("pet/size", new_size)
        self._keep_current_position_visible()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._position_restored:
            self._position_restored = True
            QTimer.singleShot(0, self._restore_position)
        if sys.platform == "darwin":
            for delay in (0, 200, 500, 1500):
                QTimer.singleShot(delay, self._pin_macos_topmost)
            if self._topmost_timer is None:
                self._topmost_timer = QTimer(self)
                self._topmost_timer.timeout.connect(self._keep_on_top)
                self._topmost_timer.start(3000)

    def _keep_on_top(self):
        if sys.platform == "darwin":
            self._pin_macos_topmost()

    def _pin_macos_topmost(self):
        pin_macos_window_level(int(self.winId()), 1000)

    def _pin_break_overlay_topmost(self):
        """休息浮层压过宠物（宠物在层级 1000，浮层用 1010）。"""
        pin_macos_window_level(int(self.break_overlay.winId()), 1010)

    def enterEvent(self, event):
        super().enterEvent(event)
        QTimer.singleShot(0, self._sync_pointer_hit)

    def leaveEvent(self, event):
        self.unsetCursor()
        self._set_pointer_inside(False)
        super().leaveEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._reposition_todo_quick_panel()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if not self._interaction_region.contains(event.pos()):
            self._pressed_badge = False
            event.ignore()
            return
        self._pressed_badge = self._todo_badge_contains(event.pos())
        self._set_pointer_inside(True)
        self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
        self.interaction.press(event.globalPos())
        event.accept()

    def mouseMoveEvent(self, event):
        self._update_cursor_for_position(event.pos())
        if self.interaction.pressed and event.buttons() & Qt.LeftButton:
            update = self.interaction.move(event.globalPos())
            if update.dragging:
                target = event.globalPos() - self.drag_position
                self.move(self._clamp_position(target, event.globalPos()))
            event.accept()
            return
        self._set_pointer_inside(self._interaction_region.contains(event.pos()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.interaction.pressed:
            result = self.interaction.release()
            if result == "drag":
                self._save_position()
            elif result == "click":
                if self._pressed_badge and self._todo_badge_contains(event.pos()):
                    self.toggle_todo_quick_panel()
            self._pressed_badge = False
            QTimer.singleShot(0, self._sync_pointer_hit)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _sync_pointer_hit(self):
        local_position = self.mapFromGlobal(QCursor.pos())
        inside = self.rect().contains(local_position) and self._interaction_region.contains(
            local_position
        )
        self._update_cursor_for_position(local_position)
        self._set_pointer_inside(inside)

    def _todo_badge_contains(self, position: QPoint) -> bool:
        return (
            hasattr(self, "todo_badge")
            and self.todo_badge.isVisible()
            and self.todo_badge.geometry().contains(position)
        )

    def _update_cursor_for_position(self, position: QPoint) -> None:
        if self._todo_badge_contains(position):
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.unsetCursor()

    def _set_pointer_inside(self, inside: bool):
        if inside == self._pointer_inside:
            return
        self._pointer_inside = inside
        if inside:
            self.interaction.pointer_enter()
        else:
            self.interaction.pointer_leave()

    def _screen_for_point(self, point: QPoint):
        screen = QGuiApplication.screenAt(point)
        if screen is not None:
            return screen
        screens = QGuiApplication.screens()
        if not screens:
            return QGuiApplication.primaryScreen()

        def distance_squared(candidate):
            geometry = candidate.availableGeometry()
            x = min(max(point.x(), geometry.left()), geometry.right())
            y = min(max(point.y(), geometry.top()), geometry.bottom())
            return (point.x() - x) ** 2 + (point.y() - y) ** 2

        return min(screens, key=distance_squared)

    def _clamp_position(self, target: QPoint, screen_point: Optional[QPoint] = None):
        reference = screen_point or QPoint(
            target.x() + self.width() // 2,
            target.y() + self.height() // 2,
        )
        screen = self._screen_for_point(reference)
        if screen is None:
            return target
        geometry = screen.availableGeometry()
        visible_x = min(MIN_VISIBLE_PIXELS, self.width())
        visible_y = min(MIN_VISIBLE_PIXELS, self.height())
        minimum_x = geometry.left() - self.width() + visible_x
        maximum_x = geometry.right() - visible_x + 1
        minimum_y = geometry.top() - self.height() + visible_y
        maximum_y = geometry.bottom() - visible_y + 1
        return QPoint(
            max(minimum_x, min(target.x(), maximum_x)),
            max(minimum_y, min(target.y(), maximum_y)),
        )

    def _save_position(self):
        self.settings.setValue("pet/position_x", self.x())
        self.settings.setValue("pet/position_y", self.y())

    def _restore_position(self):
        raw_x = self.settings.value("pet/position_x")
        raw_y = self.settings.value("pet/position_y")
        if raw_x is None or raw_y is None:
            return
        try:
            target = QPoint(int(raw_x), int(raw_y))
        except (TypeError, ValueError):
            return
        self.move(self._clamp_position(target))

    def _keep_current_position_visible(self):
        if self.isVisible():
            self.move(self._clamp_position(self.pos()))

    def _external_package_dir_from_key(self, source_key: Optional[str]) -> Optional[Path]:
        if source_key and source_key.startswith("external-package:"):
            return Path(source_key.split(":", 1)[1])
        return None

    def _package_entry_from_key(self, source_key: str) -> Optional[PetMenuEntry]:
        builtin_root = Path(resource_path("pets")).resolve()
        if source_key.startswith("builtin-package:"):
            relative = source_key.split(":", 1)[1]
            return self._package_entry_for_dir(
                builtin_root / Path(relative),
                "builtin",
                builtin_root,
            )
        external_dir = self._external_package_dir_from_key(source_key)
        if external_dir is not None:
            return self._package_entry_for_dir(external_dir, "local", builtin_root)
        return None

    def _package_entry_for_dir(
        self,
        raw_path,
        origin: str,
        builtin_root: Path,
    ) -> PetMenuEntry:
        package_dir = Path(raw_path).expanduser().resolve()
        if origin == "builtin":
            try:
                relative = package_dir.relative_to(builtin_root).as_posix()
            except ValueError:
                relative = package_dir.name
            source_key = f"builtin-package:{relative}"
        else:
            source_key = f"external-package:{package_dir}"

        try:
            package = load_pet_package(package_dir)
            return PetMenuEntry(
                package_dir=package_dir,
                source_key=source_key,
                origin=origin,
                package=package,
            )
        except PetPackageError as exc:
            return PetMenuEntry(
                package_dir=package_dir,
                source_key=source_key,
                origin=origin,
                error=str(exc),
                display_name=f"{package_dir.name}（不可用）",
            )

    def _discover_pet_entries(self) -> List[PetMenuEntry]:
        entries: List[PetMenuEntry] = []
        seen_paths = set()
        builtin_root = Path(resource_path("pets")).resolve()

        candidates = []
        for path in find_pet_directories(builtin_root):
            candidates.append((path, "builtin"))
        current_external_dir = self._external_package_dir_from_key(
            self.current_source_key
            if self.current_source_type == "package"
            else None
        )
        if current_external_dir is not None:
            candidates.append((current_external_dir, "local"))

        for raw_path, origin in candidates:
            path_key = canonical_path(raw_path)
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            entry = self._package_entry_for_dir(raw_path, origin, builtin_root)
            if entry.package is None and origin == "builtin":
                print(
                    f"[DesktopPet] skipped invalid pet {entry.package_dir}: {entry.error}",
                    file=sys.stderr,
                )
                continue
            entries.append(entry)

        duplicate_counts = {}
        for entry in entries:
            if entry.package is None:
                continue
            pet_id = entry.package.pet_id
            count = duplicate_counts.get(pet_id, 0) + 1
            duplicate_counts[pet_id] = count
            suffix = "" if count == 1 else f"-{count}"
            entry.runtime_id = f"{pet_id}{suffix}"
            entry.display_name = f"{entry.package.display_name}{suffix}"
        return entries

    def _load_manual_pet(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择互动宠物目录",
            str(Path.home()),
        )
        if not directory:
            return
        try:
            entry = self._package_entry_for_dir(
                directory,
                "local",
                Path(resource_path("pets")).resolve(),
            )
        except PetPackageError as exc:
            QMessageBox.warning(self, "无法加载互动宠物", str(exc))
            return
        if entry.package is None:
            QMessageBox.warning(self, "无法加载互动宠物", entry.error or "资源包无效")
            return
        self._load_package_entry(entry)

    def contextMenuEvent(self, event):
        if not self._interaction_region.contains(event.pos()):
            event.ignore()
            return

        menu = QMenu(self)
        package_actions = {}
        gif_actions = {}
        todo_action = None

        if self._todo_enabled and self.todo_store is not None and self.holiday_calendar is not None:
            todo_action = menu.addAction("管理待办")
            menu.addSeparator()

        package_menu = menu.addMenu("互动宠物")
        pet_entries = self._discover_pet_entries()
        valid_entries = [entry for entry in pet_entries if entry.package is not None]
        invalid_entries = [entry for entry in pet_entries if entry.package is None]

        for entry in valid_entries:
            action = package_menu.addAction(entry.display_name)
            action.setCheckable(True)
            action.setChecked(
                self.current_source_type == "package"
                and self.current_source_key == entry.source_key
            )
            package_actions[action] = entry
        if not valid_entries:
            empty_action = package_menu.addAction("未发现互动宠物")
            empty_action.setEnabled(False)

        if invalid_entries:
            package_menu.addSeparator()
            for entry in invalid_entries:
                invalid_action = package_menu.addAction(entry.display_name)
                invalid_action.setEnabled(False)

        menu.addSeparator()
        for category_name, actions in scan_actions():
            submenu = menu.addMenu(category_name)
            for display_name, gif_path in actions:
                action = submenu.addAction(display_name)
                action.setCheckable(True)
                action.setChecked(
                    self.current_source_type == "gif"
                    and self.current_source_key == self._gif_key(gif_path)
                )
                gif_actions[action] = gif_path

        menu.addSeparator()
        size_menu = menu.addMenu("大小设置")
        self._build_size_menu(size_menu)

        menu.addSeparator()
        load_pet_action = menu.addAction("加载互动宠物目录...")
        load_gif_action = menu.addAction("加载本地 GIF...")
        menu.addSeparator()
        quit_action = menu.addAction("退出宠物")

        selected = menu.exec_(self.mapToGlobal(event.pos()))
        if selected is None:
            return
        if selected == todo_action:
            self.open_todo_manager()
        elif selected in package_actions:
            self._load_package_entry(package_actions[selected])
        elif selected in gif_actions:
            self._load_gif(gif_actions[selected])
        elif selected == load_pet_action:
            self._load_manual_pet()
        elif selected == load_gif_action:
            filename, _filter = QFileDialog.getOpenFileName(
                self,
                "选择自定义宠物",
                "",
                "GIF 动图 (*.gif)",
            )
            if filename:
                self._load_gif(filename)
        elif selected == quit_action:
            self.quit_app()

    def _apply_preset(self, size):
        if hasattr(self, "_size_slider"):
            self._size_slider.setValue(size)

    def _build_size_menu(self, size_menu):
        preset_actions = []
        current_size = self.pet_size
        for label, size in PRESET_SIZES.items():
            action = size_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(current_size == size)
            action.triggered.connect(lambda _checked, value=size: self._apply_preset(value))
            preset_actions.append((action, size))

        size_menu.addSeparator()
        slider_widget = QWidget()
        slider_layout = QHBoxLayout(slider_widget)
        slider_layout.setContentsMargins(8, 2, 8, 2)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(MIN_SIZE, MAX_SIZE)
        slider.setValue(current_size)
        slider.setFixedWidth(160)
        slider.valueChanged.connect(self.set_pet_size)

        def sync_preset_checks(value):
            for action, size in preset_actions:
                action.setChecked(value == size)

        slider.valueChanged.connect(sync_preset_checks)
        slider_layout.addWidget(slider)
        slider_action = QWidgetAction(size_menu)
        slider_action.setDefaultWidget(slider_widget)
        size_menu.addAction(slider_action)

        size_menu.addSeparator()
        size_label_action = size_menu.addAction(f"当前高度: {current_size}")
        size_label_action.setEnabled(False)
        slider.valueChanged.connect(
            lambda value: size_label_action.setText(f"当前高度: {value}")
        )
        self._size_slider = slider

    def _init_todos(self):
        try:
            if self.todo_store is None:
                self.todo_store = TodoStore()
            if self.holiday_calendar is None:
                self.holiday_calendar = HolidayCalendar()
            self.todo_scheduler = TodoScheduler(
                self.todo_store,
                self.holiday_calendar,
                self,
            )
            self.todo_scheduler.badge_count_changed.connect(self.set_todo_badge_count)
            self.todo_scheduler.badge_count_changed.connect(
                lambda _count: self._refresh_todo_manager()
            )
            self.todo_scheduler.reminders_claimed.connect(self._show_todo_reminders)
            self.todo_notifier = TodoChangeNotifier(
                signal_path_for_database(self.todo_store.db_path),
                self,
            )
            self.todo_notifier.changed.connect(self._external_todo_data_changed)
            QTimer.singleShot(0, self.todo_scheduler.start)
        except Exception as exc:
            print(f"[DesktopPet] todo init failed: {exc}", file=sys.stderr)

    def set_todo_badge_count(self, count: int):
        self._todo_badge_count = max(0, count)
        if self._todo_badge_count <= 0:
            self.todo_badge.hide()
        else:
            self.todo_badge.setText("99+" if self._todo_badge_count > 99 else str(count))
            self._position_todo_badge()
            self.todo_badge.show()
            self.todo_badge.raise_()
        self._apply_effective_regions()
        if self.todo_quick_panel is not None and self.todo_quick_panel.isVisible():
            self.todo_quick_panel.refresh()
        self._reposition_todo_quick_panel()
        QTimer.singleShot(0, self._sync_pointer_hit)

    def toggle_todo_quick_panel(self):
        if not self._todo_enabled or self.todo_store is None or self.holiday_calendar is None:
            return
        if self.todo_quick_panel is None:
            self.todo_quick_panel = TodoQuickPanel(
                self.todo_store,
                self.holiday_calendar,
                self,
            )
            self.todo_quick_panel.manage_requested.connect(self.open_todo_manager)
        anchor = self.todo_badge if self.todo_badge.isVisible() else self
        self.todo_quick_panel.toggle_near(anchor)

    def _reposition_todo_quick_panel(self):
        if self.todo_quick_panel is None or not self.todo_quick_panel.isVisible():
            return
        anchor = self.todo_badge if self.todo_badge.isVisible() else self
        self.todo_quick_panel.reposition_near(anchor)

    def open_todo_manager(self, occurrence_id: Optional[int] = None):
        if not self._todo_enabled or self.todo_store is None or self.holiday_calendar is None:
            return
        if self.todo_quick_panel is not None:
            self.todo_quick_panel.hide()
        if self.todo_manager is None:
            self.todo_manager = TodoManagerWindow(
                self.todo_store,
                self.holiday_calendar,
            )
            self.todo_manager.todos_changed.connect(self._todo_data_changed)
            self.todo_manager.calendar_changed.connect(self._calendar_data_changed)
        self.todo_manager.show()
        self.todo_manager.raise_()
        self.todo_manager.activateWindow()
        if occurrence_id is not None:
            self.todo_manager.select_occurrence(occurrence_id)
        else:
            self.todo_manager.refresh()

    def _todo_data_changed(self):
        if self.todo_scheduler is not None:
            self.todo_scheduler.refresh_badge()
        self._refresh_todo_manager()
        if self.todo_notifier is not None:
            self.todo_notifier.notify_change(TODO_CHANGE_KIND)

    def _calendar_data_changed(self):
        if self.todo_scheduler is not None:
            self.todo_scheduler.refresh_badge()
        self._refresh_todo_manager()
        if self.todo_notifier is not None:
            self.todo_notifier.notify_change(CALENDAR_CHANGE_KIND)

    def _external_todo_data_changed(self, kind: str):
        if not self._todo_enabled or self.todo_store is None:
            return
        if kind == CALENDAR_CHANGE_KIND and self.holiday_calendar is not None:
            try:
                self.holiday_calendar.reload()
                self.todo_store.materialize(local_now().date(), self.holiday_calendar)
            except Exception as exc:
                print(f"[DesktopPet] calendar reload failed: {exc}", file=sys.stderr)
        if self.todo_scheduler is not None:
            self.todo_scheduler.refresh_badge()
        self._refresh_todo_manager()

    def _refresh_todo_manager(self):
        if self.todo_manager is not None and self.todo_manager.isVisible():
            self.todo_manager.refresh()
        if self.todo_quick_panel is not None and self.todo_quick_panel.isVisible():
            self.todo_quick_panel.refresh()

    def _show_todo_reminders(self, occurrences):
        if not self._todo_enabled:
            return
        if self._reminders_paused:
            return
        if not self._setting_bool("todo/notifications_enabled"):
            return
        if self.todo_bubble is None:
            self.todo_bubble = TodoReminderBubble(
                self,
                visible_ms=self._setting_int("todo/bubble_ms"),
            )
            self.todo_bubble.clicked.connect(self.open_todo_manager)
        self.todo_bubble.show_for_occurrences(list(occurrences), self)

    def closeEvent(self, event):
        if self.todo_scheduler is not None:
            self.todo_scheduler.stop()
        if self.todo_notifier is not None:
            self.todo_notifier.stop()
        if self.todo_manager is not None:
            self.todo_manager.hide()
        if self.todo_quick_panel is not None:
            self.todo_quick_panel.hide()
        if self.todo_bubble is not None:
            self.todo_bubble.hide()
        if getattr(self, "health", None) is not None:
            self.health.stop_all()
        if getattr(self, "break_overlay", None) is not None:
            self.break_overlay.hide()
        if self.tray is not None and not self._quit_requested:
            self.hide()
            event.ignore()
            return
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # M1：设置 / 托盘 / 自启
    # ------------------------------------------------------------------

    def _setting_bool(self, key: str) -> bool:
        return self.settings.value(key, DEFAULT_SETTINGS.get(key, True), type=bool)

    def _setting_int(self, key: str) -> int:
        return self.settings.value(key, DEFAULT_SETTINGS.get(key, 0), type=int)

    def _apply_saved_settings(self) -> None:
        for key in OBSOLETE_SETTINGS_KEYS:
            if self.settings.contains(key):
                self.settings.remove(key)
        self._apply_poll_interval(self._setting_int("todo/poll_minutes"))
        self.health.start()

    def _apply_poll_interval(self, minutes: int) -> None:
        if self.todo_scheduler is None:
            return
        self.todo_scheduler.poll_step_minutes = max(1, min(60, int(minutes)))
        if not self._reminders_paused:
            self.todo_scheduler.stop()
            self.todo_scheduler.start()

    def _on_setting_changed(self, key: str, value) -> None:
        if key == "pet/size":
            self.set_pet_size(int(value))
        elif key == "todo/notifications_enabled":
            if not value and self.todo_bubble is not None:
                self.todo_bubble.hide()
        elif key == "todo/bubble_ms":
            if self.todo_bubble is not None:
                self.todo_bubble.visible_ms = int(value)
        elif key == "todo/poll_minutes":
            self._apply_poll_interval(int(value))
        elif key == "sound/enabled":
            pass  # SoundManager 在播放时读取开关
        elif key == "health/enabled":
            self.health.apply_config(enabled=bool(value))
        elif key == "health/work_minutes":
            self.health.apply_config(work_minutes=int(value))
        elif key == "health/break_seconds":
            self.health.apply_config(break_seconds=int(value))
        elif key == "health/long_break_every":
            self.health.apply_config(long_break_every=int(value))
        elif key == "health/long_break_minutes":
            self.health.apply_config(long_break_minutes=int(value))
        elif key == "health/fullscreen_break":
            pass  # 下次休息开始时读取该开关

    def open_settings_window(self) -> None:
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.settings, self)
            self.settings_window.changed.connect(self._on_setting_changed)
            self.settings_window.autostart_changed.connect(self._set_autostart)
        self.settings_window.show()
        screen = self._screen_for_point(QCursor.pos())
        if screen is not None:
            frame = self.settings_window.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.settings_window.move(frame.topLeft())
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _set_autostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except Exception as exc:
            QMessageBox.warning(self, "无法设置开机自启", str(exc))
            if self.settings_window is not None:
                self.settings_window.set_autostart_checked(not enabled)
            return
        self.settings.setValue("autostart/enabled", enabled)

    def _init_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = TrayController(QIcon(resource_path("icon.png")), self)
        self.tray.manage_todo_requested.connect(self.open_todo_manager)
        self.tray.toggle_reminders_requested.connect(self.set_reminders_paused)
        self.tray.health_pause_requested.connect(self.set_health_paused)
        self.tray.health_break_now_requested.connect(self.health.start_break_now)
        self.tray.settings_requested.connect(self.open_settings_window)
        self.tray.quit_requested.connect(self.quit_app)
        self.tray.show()

    def set_health_paused(self, paused: bool) -> None:
        self.health.set_paused(bool(paused))
        if self.tray is not None:
            self.tray.set_health_paused(bool(paused))

    # ------------------------------------------------------------------
    # 健康提醒（Eye Monitor / Stretchly 风格）
    # ------------------------------------------------------------------

    def _on_health_break_started(self, kind: str, seconds: int) -> None:
        self.sound.play("remind")
        screen = self._screen_for_point(self.frameGeometry().center())
        self.break_overlay.show_break(
            kind,
            seconds,
            screen.availableGeometry(),
            fullscreen=self._setting_bool("health/fullscreen_break"),
        )
        if sys.platform == "darwin":
            # macOS 上把浮层压到宠物（层级 1000）之上，全屏强制休息时
            # 宠物不会出现在遮罩上面。
            QTimer.singleShot(0, self._pin_break_overlay_topmost)

    def _on_health_break_ticked(self, remaining: int) -> None:
        self.break_overlay.update_remaining(remaining)

    def _on_health_break_finished(self, _kind: str) -> None:
        self.break_overlay.hide()
        self.sound.play("complete")

    def _on_health_break_skipped(self, _kind: str) -> None:
        self.break_overlay.hide()

    def set_reminders_paused(self, paused: bool) -> None:
        self._reminders_paused = bool(paused)
        if self.tray is not None:
            self.tray.set_reminders_paused(self._reminders_paused)
        if self._reminders_paused:
            if self.todo_scheduler is not None:
                self.todo_scheduler.stop()
            if self.todo_bubble is not None:
                self.todo_bubble.hide()
        elif self.todo_scheduler is not None:
            self.todo_scheduler.start()

    def quit_app(self) -> None:
        self._quit_requested = True
        self.hide()
        if self.tray is not None:
            self.tray.hide()
        qApp.quit()


def main():
    install_qt_message_filter()
    app = QApplication(sys.argv)
    configure_app(app)
    pet = DesktopPet()
    pet.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
