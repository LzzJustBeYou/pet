import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from main import DesktopPet


class HealthUiIntegrationTests(unittest.TestCase):
    """通过主窗口验证健康提醒的 UI 行为。"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings = QSettings(
            str(Path(self.temp_dir.name) / "settings.ini"),
            QSettings.IniFormat,
        )
        self.pet = DesktopPet(settings=self.settings, enable_todos=False)
        self.pet.show()
        QApplication.processEvents()

    def tearDown(self):
        self.pet.close()
        self.settings.sync()
        self.temp_dir.cleanup()

    def test_break_overlay_not_visible_at_startup(self):
        # 回归：浮层必须是独立顶层窗口，不能作为子控件盖在宠物上
        self.assertTrue(self.pet.isVisible())
        self.assertFalse(self.pet.break_overlay.isVisible())
        self.assertIs(self.pet.break_overlay.window(), self.pet.break_overlay)

    def test_break_start_shows_overlay(self):
        self.pet.health.start_break_now()
        self.assertTrue(self.pet.break_overlay.isVisible())
        self.assertEqual(
            self.pet.break_overlay.title_label.text(), "休息一下"
        )
        self.assertEqual(
            self.pet.break_overlay.countdown_label.text(), "20"
        )

    def test_break_tick_updates_overlay(self):
        self.pet.health.start_break_now()
        self.pet.health._tick()
        self.assertEqual(
            self.pet.break_overlay.countdown_label.text(), "19"
        )
        self.assertEqual(self.pet.break_overlay.progress.value(), 19)

    def test_break_finish_hides_overlay(self):
        self.pet.health.start_break_now()
        self.assertTrue(self.pet.break_overlay.isVisible())
        self.pet.health._finish_break()
        self.assertFalse(self.pet.break_overlay.isVisible())

    def test_skip_button_skips_break(self):
        self.pet.health.start_break_now()
        QApplication.processEvents()
        QTest.mouseClick(
            self.pet.break_overlay.skip_button, Qt.LeftButton
        )
        self.assertFalse(self.pet.break_overlay.isVisible())
        self.assertFalse(self.pet.health.active)
        self.assertTrue(self.pet.health._work_timer.isActive())

    def test_long_break_shows_long_title(self):
        self.pet.health.long_break_every = 2
        self.pet.health._completed_breaks = 1
        self.pet.health.start_break_now()
        self.assertEqual(
            self.pet.break_overlay.title_label.text(),
            "长休息，站起来走走",
        )
        self.assertEqual(
            self.pet.break_overlay.countdown_label.text(),
            str(self.pet.health.long_break_minutes * 60),
        )

    def test_tray_pause_pauses_controller(self):
        self.pet.set_health_paused(True)
        self.assertTrue(self.pet.health.paused)
        self.assertFalse(self.pet.health._work_timer.isActive())
        if self.pet.tray is not None:
            self.assertTrue(self.pet.tray._health_pause_action.isChecked())

    def test_settings_disable_stops_timer(self):
        self.assertTrue(self.pet.health._work_timer.isActive())
        self.pet._on_setting_changed("health/enabled", False)
        self.assertFalse(self.pet.health.enabled)
        self.assertFalse(self.pet.health._work_timer.isActive())
