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
        self.assertEqual(self.window.opacity_slider.value(), 100)
        self.assertTrue(self.window.pinned_check.isChecked())
        self.assertTrue(self.window.interactive_check.isChecked())
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

    def test_opacity_scaled_to_percent(self):
        self.window.opacity_slider.setValue(60)
        self.assertIn(("pet/opacity", 0.6), self.changes)
        self.assertAlmostEqual(
            self.settings.value("pet/opacity", type=float), 0.6
        )

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
        self.settings.setValue("pet/opacity", 0.5)
        self.settings.setValue("pet/pinned", False)
        reloaded = SettingsWindow(self.settings)
        self.assertEqual(reloaded.opacity_slider.value(), 50)
        self.assertFalse(reloaded.pinned_check.isChecked())
        reloaded.close()
