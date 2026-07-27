import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QMenu, qApp, QFileDialog, QSlider, QWidgetAction, QHBoxLayout
from PyQt5.QtCore import Qt, QPoint, QSize, QTimer, QSettings
from PyQt5.QtGui import QMovie, QIcon


def resource_path(relative_path):
    """获取资源的绝对路径。兼容开发环境和 PyInstaller 打包后的环境"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def scan_actions(actions_dir="actions"):
    """
    扫描 actions/ 目录，自动发现所有动作。
    约定：子目录 = 分类（菜单），目录内的 .gif 文件 = 动作，文件名（去扩展名）= 显示名。

    返回: [(分类名, [(显示名, 完整路径), ...]), ...]
    只需把 GIF 放进 actions/ 的任意子目录即可自动出现在菜单中。
    """
    categories = []
    target_dir = resource_path(actions_dir)
    if not os.path.isdir(target_dir):
        return categories

    for category in sorted(os.listdir(target_dir)):
        cat_path = os.path.join(target_dir, category)
        if not os.path.isdir(cat_path):
            continue
        actions = []
        for f in sorted(os.listdir(cat_path)):
            if f.lower().endswith(".gif"):
                full_path = os.path.join(cat_path, f)
                display_name = os.path.splitext(f)[0]
                actions.append((display_name, full_path))
        if actions:
            categories.append((category, actions))
    return categories


# --- 大小预设 ---
PRESET_SIZES = {
    "小 (80×80)": 80,
    "中 (100×100)": 100,
    "大 (150×150)": 150,
    "超大 (200×200)": 200,
}
MIN_SIZE = 40
MAX_SIZE = 300
DEFAULT_SIZE = 100


class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        # --- 宠物基础设置 ---
        self.settings = QSettings("PetApp", "DesktopPet")
        saved_size = self.settings.value("pet/size", DEFAULT_SIZE, type=int)
        saved_size = max(MIN_SIZE, min(MAX_SIZE, saved_size))  # 范围约束
        self.pet_width = saved_size
        self.pet_height = saved_size

        # 自动发现所有动作，默认"臭臭小八"，找不到则取第一个
        DEFAULT_PET = "臭臭小八"
        all_actions = scan_actions()
        self.current_gif = None
        for _cat, actions in all_actions:
            for name, path in actions:
                if name == DEFAULT_PET:
                    self.current_gif = path
                    break
            if self.current_gif:
                break
        if not self.current_gif and all_actions and all_actions[0][1]:
            self.current_gif = all_actions[0][1][0][1]

        self.initUI()
        self.dragPosition = QPoint()

    def initUI(self):
        # 窗口和透明设置
        # - macOS: 窗口层级由 _pin_macos_topmost() 通过 objc_msgSend 控制，
        #   不使用 Qt.WindowStaysOnTopHint，避免 Qt 与 ctypes 设置冲突
        # - Windows/Linux: 使用 Qt.WindowStaysOnTopHint 保持顶层
        flags = Qt.FramelessWindowHint | Qt.Tool
        if sys.platform != "darwin":
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # 不抢焦点
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)  # 不激活时也显示

        # 标签设置
        self.label = QLabel(self)
        self.label.setFixedSize(self.pet_width, self.pet_height)
        self.resize(self.pet_width, self.pet_height)

        # 首次加载
        if self.current_gif:
            self._load_gif(self.current_gif)

    def _load_gif(self, gif_path):
        """加载并播放 GIF"""
        self.movie = QMovie(gif_path)
        self.movie.setScaledSize(QSize(self.pet_width, self.pet_height))
        self.label.setMovie(self.movie)
        self.movie.start()

    def set_pet_size(self, new_size):
        """设置宠物大小并持久化"""
        new_size = max(MIN_SIZE, min(MAX_SIZE, new_size))
        if new_size == self.pet_width:
            return
        self.pet_width = new_size
        self.pet_height = new_size
        self.resize(new_size, new_size)
        self.label.setFixedSize(new_size, new_size)
        if hasattr(self, "movie") and self.movie is not None:
            self.movie.setScaledSize(QSize(new_size, new_size))
        self.settings.setValue("pet/size", new_size)

    def showEvent(self, event):
        """窗口显示后，macOS 上提升窗口层级确保永远在最顶层。"""
        super().showEvent(event)
        if sys.platform == "darwin":
            for delay in (0, 200, 500, 1500):
                QTimer.singleShot(delay, self._pin_macos_topmost)
            self._topmost_timer = QTimer(self)
            self._topmost_timer.timeout.connect(self._keep_on_top)
            self._topmost_timer.start(3000)  # 每 3 秒双重确认

    def _keep_on_top(self):
        """定时保持顶层：仅检查和恢复窗口层级，不调用 raise/orderFront 避免抢焦点。"""
        self._pin_macos_topmost()

    def _pin_macos_topmost(self):
        """通过 objc_msgSend 将 NSWindow 层级提升至 kCGOverlayWindowLevel，
        高于全屏应用、Dock、菜单栏，且在所有桌面空间可见。"""
        import ctypes
        import ctypes.util
        from ctypes import c_void_p, c_long, c_char_p, CFUNCTYPE, cast

        try:
            objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
            sel_reg = objc.sel_registerName
            sel_reg.restype = c_void_p
            sel_reg.argtypes = [c_char_p]

            msg_id = CFUNCTYPE(c_void_p, c_void_p, c_void_p)
            msg_void_long = CFUNCTYPE(None, c_void_p, c_void_p, c_long)
            msg_long = CFUNCTYPE(c_long, c_void_p, c_void_p)

            win_id = int(self.winId())
            if win_id == 0:
                return

            nswindow = cast(objc.objc_msgSend, msg_id)(
                c_void_p(win_id), sel_reg(b"window")
            )
            if not nswindow:
                return

            # 检查当前层级，只在需要时设置，避免无谓的窗口刷新
            current = cast(objc.objc_msgSend, msg_long)(
                nswindow, sel_reg(b"level")
            )
            # kCGOverlayWindowLevel → 通过 CoreGraphics 获取
            TARGET = 1000

            if current != TARGET:
                cast(objc.objc_msgSend, msg_void_long)(
                    nswindow, sel_reg(b"setLevel:"), c_long(TARGET)
                )
                # CanJoinAllSpaces(1) | FullScreenAuxiliary(32)
                # Stationary(4) 会锚定屏幕而非 Space，与 CanJoinAllSpaces 冲突
                cast(objc.objc_msgSend, msg_void_long)(
                    nswindow, sel_reg(b"setCollectionBehavior:"), c_long(33)
                )
        except Exception as e:
            print(f"[DesktopPet] pin failed: {e}", file=sys.stderr)

    def change_pet(self, new_gif_path):
        """核心功能：平滑切换 GIF 动图"""
        self.movie.stop()
        self.current_gif = new_gif_path
        self._load_gif(new_gif_path)

    # --- 鼠标左键拖拽功能 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragPosition = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.dragPosition)
            event.accept()

    # --- 右键菜单功能 ---
    def contextMenuEvent(self, event):
        menu = QMenu(self)

        # 动态扫描，构建分类子菜单
        categories = scan_actions()
        for cat_name, actions in categories:
            sub_menu = menu.addMenu(cat_name)
            for display_name, gif_path in actions:
                action = sub_menu.addAction(display_name)
                action.setData(gif_path)

        menu.addSeparator()

        # --- 大小子菜单 ---
        size_menu = menu.addMenu("大小设置")
        self._build_size_menu(size_menu)

        menu.addSeparator()
        load_action = menu.addAction("加载本地 GIF...")
        menu.addSeparator()
        quit_action = menu.addAction("退出宠物")

        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action is None:
            return

        if action == load_action:
            file_name, _ = QFileDialog.getOpenFileName(
                self, "选择自定义宠物", "", "GIF 动图 (*.gif)"
            )
            if file_name:
                self.change_pet(file_name)
        elif action == quit_action:
            qApp.quit()
        elif action.data() is not None:
            self.change_pet(action.data())

    def _apply_preset(self, size):
        """应用预设大小：同步滑块并更新宠物"""
        if hasattr(self, "_size_slider"):
            self._size_slider.setValue(size)

    def _build_size_menu(self, size_menu):
        """构建大小子菜单：预设 + 滑块 + 当前值显示"""
        preset_sizes_rev = {v: k for k, v in PRESET_SIZES.items()}

        # 预设选项（checkable）
        group = []
        current_size = self.pet_width
        for label, size in PRESET_SIZES.items():
            action = size_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(current_size == size)
            action.triggered.connect(
                lambda _, s=size: self._apply_preset(s)
            )
            group.append(action)

        size_menu.addSeparator()

        # 自定义滑块
        slider_widget = QWidget()
        slider_layout = QHBoxLayout(slider_widget)
        slider_layout.setContentsMargins(8, 2, 8, 2)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(MIN_SIZE, MAX_SIZE)
        slider.setValue(current_size)
        slider.setFixedWidth(160)

        # 滑块拖动时实时更新宠物大小
        slider.valueChanged.connect(self.set_pet_size)

        # 滑块值变更时同步预设勾选状态
        def sync_preset_checks(v):
            for a in group:
                a.setChecked(v in preset_sizes_rev)

        slider.valueChanged.connect(sync_preset_checks)
        slider_layout.addWidget(slider)
        slider_action = QWidgetAction(size_menu)
        slider_action.setDefaultWidget(slider_widget)
        size_menu.addAction(slider_action)

        size_menu.addSeparator()

        # 当前尺寸标签
        self._size_label_action = size_menu.addAction(
            f"当前: {current_size}×{current_size}"
        )
        self._size_label_action.setEnabled(False)

        def update_label(v):
            self._size_label_action.setText(f"当前: {v}×{v}")

        slider.valueChanged.connect(update_label)

        # 保存引用：预设点击时需要同步滑块
        self._size_slider = slider
        self._size_presets = group


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 应用图标
    # - macOS: 图标由 .app bundle 内嵌的 icon.icns 提供，系统自动处理圆角和缩放
    # - Windows: 需手动设置图标用于任务栏显示
    if sys.platform == "win32":
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
    # macOS 不需要 setWindowIcon，系统会从 .icns 读取

    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())
