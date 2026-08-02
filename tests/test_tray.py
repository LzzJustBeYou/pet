import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon

from tray_controller import TrayController


class TrayControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_menu_actions_emit_signals(self):
        tray = TrayController(QIcon())
        emitted = []
        tray.toggle_visibility_requested.connect(lambda: emitted.append("toggle"))
        tray.manage_todo_requested.connect(lambda: emitted.append("manage"))
        tray.settings_requested.connect(lambda: emitted.append("settings"))
        tray.quit_requested.connect(lambda: emitted.append("quit"))
        paused = []
        tray.toggle_reminders_requested.connect(paused.append)

        actions = tray._menu.actions()
        texts = [action.text() for action in actions]
        self.assertEqual(
            texts,
            ["显示/隐藏宠物", "", "管理待办", "暂停提醒", "设置", "", "退出"],
        )

        actions[0].trigger()
        actions[2].trigger()
        actions[4].trigger()
        actions[6].trigger()
        self.assertEqual(emitted, ["toggle", "manage", "settings", "quit"])

        actions[3].setChecked(True)
        self.assertEqual(paused, [True])

    def test_set_reminders_paused_syncs_checkbox_without_signal(self):
        tray = TrayController(QIcon())
        paused = []
        tray.toggle_reminders_requested.connect(paused.append)
        tray.set_reminders_paused(True)
        actions = tray._menu.actions()
        self.assertTrue(actions[3].isChecked())
        self.assertEqual(paused, [])
        tray.hide()

    def test_trigger_activation_toggles_visibility(self):
        tray = TrayController(QIcon())
        emitted = []
        tray.toggle_visibility_requested.connect(lambda: emitted.append(True))
        tray._on_activated(QSystemTrayIcon.Context)
        tray._on_activated(QSystemTrayIcon.Trigger)
        self.assertEqual(emitted, [True])
        tray.hide()
