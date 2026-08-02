import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from tray_controller import TrayController


class TrayControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_menu_actions_emit_signals(self):
        tray = TrayController(QIcon())
        emitted = []
        tray.manage_todo_requested.connect(lambda: emitted.append("manage"))
        tray.health_break_now_requested.connect(lambda: emitted.append("break_now"))
        tray.settings_requested.connect(lambda: emitted.append("settings"))
        tray.quit_requested.connect(lambda: emitted.append("quit"))
        paused = []
        tray.toggle_reminders_requested.connect(paused.append)
        health_paused = []
        tray.health_pause_requested.connect(health_paused.append)

        actions = tray._menu.actions()
        texts = [action.text() for action in actions]
        self.assertEqual(
            texts,
            [
                "管理待办",
                "",
                "健康提醒",
                "",
                "暂停提醒",
                "设置",
                "",
                "退出",
            ],
        )

        actions[0].trigger()
        health_actions = actions[2].menu().actions()
        self.assertEqual(
            [action.text() for action in health_actions],
            ["暂停提醒", "立即休息"],
        )
        health_actions[0].setChecked(True)
        health_actions[1].trigger()
        actions[5].trigger()
        actions[7].trigger()
        self.assertEqual(
            emitted,
            ["manage", "break_now", "settings", "quit"],
        )
        self.assertEqual(health_paused, [True])

        actions[4].setChecked(True)
        self.assertEqual(paused, [True])

    def test_set_reminders_paused_syncs_checkbox_without_signal(self):
        tray = TrayController(QIcon())
        paused = []
        tray.toggle_reminders_requested.connect(paused.append)
        tray.set_reminders_paused(True)
        actions = tray._menu.actions()
        self.assertTrue(actions[4].isChecked())
        self.assertEqual(paused, [])
        tray.hide()

    def test_set_health_paused_syncs_checkbox_without_signal(self):
        tray = TrayController(QIcon())
        health_paused = []
        tray.health_pause_requested.connect(health_paused.append)
        tray.set_health_paused(True)
        health_actions = tray._menu.actions()[2].menu().actions()
        self.assertTrue(health_actions[0].isChecked())
        self.assertEqual(health_paused, [])
        tray.hide()

    def test_menu_has_no_show_hide_option(self):
        tray = TrayController(QIcon())
        texts = [action.text() for action in tray._menu.actions()]
        self.assertNotIn("显示/隐藏宠物", texts)
        self.assertNotIn("显示宠物", texts)
        self.assertNotIn("隐藏宠物", texts)
        tray.hide()
