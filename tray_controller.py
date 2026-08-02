"""系统托盘控制器（M1）。"""

from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu, QSystemTrayIcon


class TrayController(QObject):
    toggle_visibility_requested = pyqtSignal()
    manage_todo_requested = pyqtSignal()
    toggle_reminders_requested = pyqtSignal(bool)
    health_pause_requested = pyqtSignal(bool)
    health_break_now_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, icon: QIcon, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("桌面宠物 DesktopPet")

        self._menu = QMenu()
        toggle_action = self._menu.addAction("显示/隐藏宠物")
        toggle_action.triggered.connect(self.toggle_visibility_requested.emit)
        self._menu.addSeparator()

        manage_action = self._menu.addAction("管理待办")
        manage_action.triggered.connect(self.manage_todo_requested.emit)
        self._menu.addSeparator()

        health_menu = self._menu.addMenu("健康提醒")
        self._health_pause_action = health_menu.addAction("暂停提醒")
        self._health_pause_action.setCheckable(True)
        self._health_pause_action.toggled.connect(
            self.health_pause_requested.emit
        )
        break_now_action = health_menu.addAction("立即休息")
        break_now_action.triggered.connect(
            self.health_break_now_requested.emit
        )
        self._menu.addSeparator()

        self._reminders_action = self._menu.addAction("暂停提醒")
        self._reminders_action.setCheckable(True)
        self._reminders_action.toggled.connect(
            self.toggle_reminders_requested.emit
        )
        settings_action = self._menu.addAction("设置")
        settings_action.triggered.connect(self.settings_requested.emit)
        self._menu.addSeparator()

        quit_action = self._menu.addAction("退出")
        quit_action.triggered.connect(self.quit_requested.emit)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def set_reminders_paused(self, paused: bool) -> None:
        self._reminders_action.blockSignals(True)
        self._reminders_action.setChecked(bool(paused))
        self._reminders_action.blockSignals(False)

    def set_health_paused(self, paused: bool) -> None:
        self._health_pause_action.blockSignals(True)
        self._health_pause_action.setChecked(bool(paused))
        self._health_pause_action.blockSignals(False)

    def _on_activated(
        self,
        reason: QSystemTrayIcon.ActivationReason,
    ) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_visibility_requested.emit()
