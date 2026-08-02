import plistlib
import sys
import types
import unittest
from unittest.mock import patch

import autostart


class AutostartContentTests(unittest.TestCase):
    def test_macos_plist_content_roundtrip(self):
        payload = plistlib.loads(
            autostart.macos_plist_content(["/usr/bin/python", "main.py"])
        )
        self.assertEqual(payload["Label"], autostart.APP_LABEL)
        self.assertEqual(
            payload["ProgramArguments"], ["/usr/bin/python", "main.py"]
        )
        self.assertTrue(payload["RunAtLoad"])

    def test_linux_desktop_content_has_exec(self):
        content = autostart.linux_desktop_content(["/usr/bin/python", "main.py"])
        self.assertIn("Name=DesktopPet", content)
        self.assertIn('Exec="/usr/bin/python" "main.py"', content)

    def test_command_frozen_uses_sys_executable(self):
        with patch.object(autostart.sys, "frozen", True, create=True):
            self.assertEqual(autostart.command_for_autostart(), [sys.executable])

    def test_command_dev_uses_main_script(self):
        with patch.object(autostart.sys, "frozen", False, create=True):
            command = autostart.command_for_autostart()
        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith("main.py"))

    def test_windows_run_key_path(self):
        self.assertEqual(
            autostart.windows_run_key_path(),
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        )

    def test_set_autostart_dispatches_to_platform(self):
        with patch.object(autostart.sys, "platform", "darwin"), \
                patch.object(autostart, "_set_macos_autostart") as mac:
            autostart.set_autostart(True)
            mac.assert_called_once_with(True)

    def test_unsupported_platform_raises(self):
        with patch.object(autostart.sys, "platform", "plan9"), \
                self.assertRaises(RuntimeError):
            autostart.set_autostart(True)


class WindowsAutostartTests(unittest.TestCase):
    """在非 Windows 平台上通过注入假的 winreg 模块测试注册表逻辑。"""

    def setUp(self):
        fake = types.ModuleType("winreg")
        fake.HKEY_CURRENT_USER = object()
        fake.KEY_SET_VALUE = 1
        fake.REG_SZ = 1
        fake.OpenKey = unittest.mock.MagicMock()
        fake.SetValueEx = unittest.mock.MagicMock()
        fake.QueryValueEx = unittest.mock.MagicMock()
        fake.DeleteValue = unittest.mock.MagicMock()
        self._fake = fake
        self._original = sys.modules.get("winreg")
        sys.modules["winreg"] = fake

    def tearDown(self):
        if self._original is None:
            sys.modules.pop("winreg", None)
        else:
            sys.modules["winreg"] = self._original

    def test_write_run_entry(self):
        autostart.write_windows_run_entry(r"C:\apps\DesktopPet.exe")
        args = self._fake.SetValueEx.call_args[0]
        self.assertEqual(args[1], "DesktopPet")
        self.assertEqual(args[4], r"C:\apps\DesktopPet.exe")

    def test_autostart_value_missing_returns_none(self):
        self._fake.OpenKey.side_effect = FileNotFoundError
        self.assertIsNone(autostart._windows_autostart_value())

    def test_enable_windows_autostart_writes_executable(self):
        autostart._set_windows_autostart(True)
        args = self._fake.SetValueEx.call_args[0]
        self.assertEqual(args[1], "DesktopPet")
        self.assertEqual(args[4], sys.executable)

    def test_disable_windows_autostart_deletes_value(self):
        autostart._set_windows_autostart(False)
        self._fake.DeleteValue.assert_called_once()
