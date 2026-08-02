"""集中设置面板（M1）。"""

from typing import Any, Dict, Optional

from PyQt5.QtCore import QSettings, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


DEFAULT_SETTINGS: Dict[str, Any] = {
    "pet/size": 100,
    "pet/opacity": 1.0,
    "pet/pinned": True,
    "pet/interactive": True,
    "todo/notifications_enabled": True,
    "todo/bubble_ms": 8000,
    "todo/poll_minutes": 5,
    "sound/enabled": False,
    "autostart/enabled": False,
}

POLL_CHOICES = [("1 分钟", 1), ("5 分钟", 5)]


def read_setting(settings: QSettings, key: str) -> Any:
    default = DEFAULT_SETTINGS[key]
    if isinstance(default, bool):
        return settings.value(key, default, type=bool)
    if isinstance(default, float):
        return settings.value(key, default, type=float)
    return settings.value(key, default, type=int)


class SettingsWindow(QWidget):
    changed = pyqtSignal(str, object)  # (key, value)
    autostart_changed = pyqtSignal(bool)

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.Window)
        self._settings = settings
        self.setWindowTitle("设置")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        # ── 宠物 ──
        pet_group = QGroupBox("宠物")
        pet_form = QFormLayout(pet_group)

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(40, 300)
        self.size_slider.setValue(int(read_setting(settings, "pet/size")))
        self.size_value_label = QLabel(f"{self.size_slider.value()} px")
        size_row = QHBoxLayout()
        size_row.addWidget(self.size_slider, 1)
        size_row.addWidget(self.size_value_label)
        pet_form.addRow("大小", size_row)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 100)
        opacity_value = round(float(read_setting(settings, "pet/opacity")) * 100)
        self.opacity_slider.setValue(max(30, min(100, opacity_value)))
        self.opacity_value_label = QLabel(f"{self.opacity_slider.value()}%")
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value_label)
        pet_form.addRow("透明度", opacity_row)

        self.pinned_check = QCheckBox("窗口置顶")
        self.pinned_check.setChecked(bool(read_setting(settings, "pet/pinned")))
        pet_form.addRow("", self.pinned_check)

        self.interactive_check = QCheckBox("悬停/拖拽动画")
        self.interactive_check.setChecked(
            bool(read_setting(settings, "pet/interactive"))
        )
        pet_form.addRow("", self.interactive_check)
        layout.addWidget(pet_group)

        # ── 待办 ──
        todo_group = QGroupBox("待办")
        todo_form = QFormLayout(todo_group)

        self.notifications_check = QCheckBox("到点弹出提醒气泡")
        self.notifications_check.setChecked(
            bool(read_setting(settings, "todo/notifications_enabled"))
        )
        todo_form.addRow("", self.notifications_check)

        self.bubble_spin = QSpinBox()
        self.bubble_spin.setRange(3000, 30000)
        self.bubble_spin.setSingleStep(1000)
        self.bubble_spin.setSuffix(" ms")
        self.bubble_spin.setValue(int(read_setting(settings, "todo/bubble_ms")))
        todo_form.addRow("气泡时长", self.bubble_spin)

        self.poll_combo = QComboBox()
        for label, value in POLL_CHOICES:
            self.poll_combo.addItem(label, value)
        poll_value = int(read_setting(settings, "todo/poll_minutes"))
        poll_index = self.poll_combo.findData(poll_value)
        if poll_index >= 0:
            self.poll_combo.setCurrentIndex(poll_index)
        todo_form.addRow("提醒检查间隔", self.poll_combo)
        layout.addWidget(todo_group)

        # ── 声音 ──
        sound_group = QGroupBox("声音")
        sound_form = QFormLayout(sound_group)
        self.sound_check = QCheckBox("启用音效（M3 生效）")
        self.sound_check.setChecked(bool(read_setting(settings, "sound/enabled")))
        sound_form.addRow("", self.sound_check)
        layout.addWidget(sound_group)

        # ── 启动 ──
        startup_group = QGroupBox("启动")
        startup_form = QFormLayout(startup_group)
        self.autostart_check = QCheckBox("开机自动启动")
        self.autostart_check.setChecked(
            bool(read_setting(settings, "autostart/enabled"))
        )
        startup_form.addRow("", self.autostart_check)
        layout.addWidget(startup_group)

        layout.addStretch()

        # 先加载完再连接信号，避免初始化回写
        self.size_slider.valueChanged.connect(self._size_changed)
        self.opacity_slider.valueChanged.connect(self._opacity_changed)
        self.pinned_check.toggled.connect(
            lambda checked: self._emit("pet/pinned", bool(checked))
        )
        self.interactive_check.toggled.connect(
            lambda checked: self._emit("pet/interactive", bool(checked))
        )
        self.notifications_check.toggled.connect(
            lambda checked: self._emit("todo/notifications_enabled", bool(checked))
        )
        self.bubble_spin.valueChanged.connect(
            lambda value: self._emit("todo/bubble_ms", int(value))
        )
        self.poll_combo.currentIndexChanged.connect(self._poll_changed)
        self.sound_check.toggled.connect(
            lambda checked: self._emit("sound/enabled", bool(checked))
        )
        self.autostart_check.toggled.connect(self._autostart_toggled)

    def _size_changed(self, value: int) -> None:
        self.size_value_label.setText(f"{value} px")
        self._emit("pet/size", int(value))

    def _opacity_changed(self, value: int) -> None:
        self.opacity_value_label.setText(f"{value}%")
        self._emit("pet/opacity", round(value / 100.0, 2))

    def _poll_changed(self, _index: int) -> None:
        self._emit("todo/poll_minutes", int(self.poll_combo.currentData()))

    def _autostart_toggled(self, checked: bool) -> None:
        # 由 DesktopPet 执行平台写入成功后再落盘，失败时回调用 set_autostart_checked
        self.autostart_changed.emit(bool(checked))

    def set_autostart_checked(self, checked: bool) -> None:
        self.autostart_check.blockSignals(True)
        self.autostart_check.setChecked(bool(checked))
        self.autostart_check.blockSignals(False)

    def _emit(self, key: str, value: Any) -> None:
        self._settings.setValue(key, value)
        self.changed.emit(key, value)
