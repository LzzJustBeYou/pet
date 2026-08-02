import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from main import DesktopPet


class SettingsUiIntegrationTests(unittest.TestCase):
    """通过真实信号链路验证设置面板与主窗口联动。"""

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

    def tearDown(self):
        self.pet.close()
        self.settings.sync()
        self.temp_dir.cleanup()

    def _open_settings(self):
        self.pet.open_settings_window()
        self.assertIsNotNone(self.pet.settings_window)
        return self.pet.settings_window

    def test_size_slider_resizes_pet(self):
        window = self._open_settings()
        window.size_slider.setValue(150)
        self.assertEqual(self.pet.pet_size, 150)

    def test_health_toggle_disables_controller(self):
        window = self._open_settings()
        self.assertTrue(self.pet.health.enabled)
        window.health_enabled_check.setChecked(False)
        self.assertFalse(self.pet.health.enabled)
        self.assertFalse(self.pet.health._work_timer.isActive())

    def test_health_spins_reconfigure_controller(self):
        window = self._open_settings()
        window.work_minutes_spin.setValue(10)
        window.break_seconds_spin.setValue(30)
        self.assertEqual(self.pet.health.work_minutes, 10)
        self.assertEqual(self.pet.health.break_seconds, 30)

    def test_autostart_toggle_writes_platform_and_settings(self):
        with patch("main.set_autostart") as mock_set:
            window = self._open_settings()
            window.autostart_check.setChecked(True)
            mock_set.assert_called_once_with(True)
            self.assertTrue(
                self.settings.value("autostart/enabled", type=bool)
            )

    def test_autostart_failure_reverts_checkbox(self):
        with patch("main.set_autostart", side_effect=RuntimeError("boom")), \
                patch("main.QMessageBox.warning") as mock_warning:
            window = self._open_settings()
            window.autostart_check.setChecked(True)
            self.assertFalse(window.autostart_check.isChecked())
            mock_warning.assert_called_once()
