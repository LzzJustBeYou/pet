import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from settings_window import DEFAULT_SETTINGS, SettingsWindow


class SettingsWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings = QSettings(
            str(Path(self.temp_dir.name) / "settings.ini"),
            QSettings.IniFormat,
        )
        self.window = SettingsWindow(self.settings)
        self.changes = []
        self.autostart_events = []
        self.window.changed.connect(
            lambda key, value: self.changes.append((key, value))
        )
        self.window.autostart_changed.connect(self.autostart_events.append)

    def tearDown(self):
        self.window.close()
        self.settings.sync()
        self.temp_dir.cleanup()

    def test_defaults_when_settings_empty(self):
        self.assertEqual(
            self.window.size_slider.value(), DEFAULT_SETTINGS["pet/size"]
        )
        self.assertTrue(self.window.notifications_check.isChecked())
        self.assertEqual(
            self.window.bubble_spin.value(), DEFAULT_SETTINGS["todo/bubble_ms"]
        )
        self.assertEqual(self.window.poll_combo.currentData(), 5)
        self.assertFalse(self.window.sound_check.isChecked())
        self.assertFalse(self.window.autostart_check.isChecked())

    def test_size_slider_emits_and_persists(self):
        self.window.size_slider.setValue(150)
        self.assertIn(("pet/size", 150), self.changes)
        self.assertEqual(self.settings.value("pet/size", type=int), 150)

    def test_poll_combo_emits_integer(self):
        self.window.poll_combo.setCurrentIndex(0)
        self.assertEqual(self.changes[-1], ("todo/poll_minutes", 1))
        self.assertEqual(self.settings.value("todo/poll_minutes", type=int), 1)

    def test_bubble_duration_emits(self):
        self.window.bubble_spin.setValue(12000)
        self.assertEqual(self.changes[-1], ("todo/bubble_ms", 12000))

    def test_autostart_toggle_emits_without_persisting(self):
        self.window.autostart_check.setChecked(True)
        self.assertEqual(self.autostart_events, [True])
        self.assertFalse(self.settings.contains("autostart/enabled"))

    def test_set_autostart_checked_reverts_without_signal(self):
        self.window.autostart_check.setChecked(True)
        self.window.set_autostart_checked(False)
        self.assertFalse(self.window.autostart_check.isChecked())
        self.assertEqual(self.autostart_events, [True])

    def test_loaded_values_reflected_from_settings(self):
        self.settings.setValue("pet/size", 150)
        self.settings.setValue("todo/bubble_ms", 12000)
        reloaded = SettingsWindow(self.settings)
        self.assertEqual(reloaded.size_slider.value(), 150)
        self.assertEqual(reloaded.bubble_spin.value(), 12000)
        reloaded.close()

    def test_health_defaults_when_settings_empty(self):
        self.assertTrue(self.window.health_enabled_check.isChecked())
        self.assertFalse(self.window.fullscreen_break_check.isChecked())
        self.assertEqual(self.window.work_minutes_spin.value(), 20)
        self.assertEqual(self.window.break_seconds_spin.value(), 20)
        self.assertEqual(self.window.long_break_every_spin.value(), 4)
        self.assertEqual(self.window.long_break_minutes_spin.value(), 5)

    def test_health_toggle_emits_and_persists(self):
        self.window.health_enabled_check.setChecked(False)
        self.assertIn(("health/enabled", False), self.changes)
        self.assertFalse(self.settings.value("health/enabled", type=bool))

    def test_fullscreen_break_toggle_emits_and_persists(self):
        self.window.fullscreen_break_check.setChecked(True)
        self.assertIn(("health/fullscreen_break", True), self.changes)
        self.assertTrue(self.settings.value("health/fullscreen_break", type=bool))

    def test_health_spins_emit_and_persist(self):
        self.window.work_minutes_spin.setValue(10)
        self.assertEqual(self.changes[-1], ("health/work_minutes", 10))
        self.assertEqual(
            self.settings.value("health/work_minutes", type=int), 10
        )
        self.window.long_break_minutes_spin.setValue(8)
        self.assertEqual(
            self.changes[-1], ("health/long_break_minutes", 8)
        )
