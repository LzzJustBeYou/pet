import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPoint, QSettings, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from holiday_calendar import HolidayCalendar
from main import DesktopPet
from todo_models import local_now
from todo_notifier import TODO_CHANGE_KIND
from todo_store import TodoStore


ROOT = Path(__file__).resolve().parents[1]


class DesktopPetTests(unittest.TestCase):
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

    def test_existing_gif_remains_first_start_default(self):
        self.assertEqual(self.pet.current_source_type, "gif")
        self.assertTrue(self.pet.current_gif.endswith("臭臭小八.gif"))

    def test_pet_window_is_always_on_top(self):
        self.assertTrue(self.pet.windowFlags() & Qt.WindowStaysOnTopHint)
        if sys.platform == "darwin":
            with patch("main.DesktopPet._pin_macos_topmost") as mock_pin:
                self.pet.show()
                self.app.processEvents()
                QTest.qWait(50)
                self.assertGreaterEqual(mock_pin.call_count, 1)

    def test_switches_to_bundled_interactive_pet(self):
        entry = next(
            item
            for item in self.pet._discover_pet_entries()
            if item.origin == "builtin" and item.package is not None
        )

        self.assertTrue(self.pet._load_package_entry(entry, show_error=False))
        self.assertEqual(self.pet.current_source_type, "package")
        self.assertEqual((self.pet.width(), self.pet.height()), (92, 100))
        self.assertFalse(self.pet._interaction_region.isEmpty())

    def test_duplicate_ids_receive_visible_numeric_suffixes(self):
        duplicate_dir = Path(self.temp_dir.name) / "duplicate"
        shutil.copytree(ROOT / "pets" / "xiaoba", duplicate_dir)
        self.pet.current_source_type = "package"
        self.pet.current_source_key = f"external-package:{duplicate_dir.resolve()}"

        names = [
            entry.display_name
            for entry in self.pet._discover_pet_entries()
            if entry.package is not None and entry.package.pet_id == "xiaoba"
        ]
        self.assertEqual(names[0], "小八")
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(any(name.startswith("小八-") for name in names[1:]))

    def test_user_home_pet_directory_is_not_auto_discovered(self):
        fake_home = Path(self.temp_dir.name) / "home"
        auto_dir = fake_home / ".codex" / "pets" / "auto-xiaoba"
        shutil.copytree(ROOT / "pets" / "xiaoba", auto_dir)

        with patch.object(Path, "home", return_value=fake_home):
            names = [
                entry.display_name
                for entry in self.pet._discover_pet_entries()
                if entry.package is not None and entry.package.pet_id == "xiaoba"
            ]

        self.assertEqual(names, ["小八"])

    def test_previous_manual_package_history_is_ignored(self):
        duplicate_dir = Path(self.temp_dir.name) / "duplicate"
        shutil.copytree(ROOT / "pets" / "xiaoba", duplicate_dir)
        self.settings.setValue(
            "pet/manual_package_dirs",
            f'["{str(duplicate_dir).replace(chr(92), chr(92) * 2)}"]',
        )

        names = [
            entry.display_name
            for entry in self.pet._discover_pet_entries()
            if entry.package is not None and entry.package.pet_id == "xiaoba"
        ]

        self.assertEqual(names, ["小八"])

    def test_restores_current_external_package_only(self):
        external_dir = Path(self.temp_dir.name) / "external"
        shutil.copytree(ROOT / "pets" / "xiaoba", external_dir)
        self.settings.setValue("pet/source_type", "package")
        self.settings.setValue("pet/source_key", f"external-package:{external_dir}")

        self.pet.close()
        self.pet = DesktopPet(settings=self.settings, enable_todos=False)

        self.assertEqual(self.pet.current_source_type, "package")
        self.assertEqual(self.pet.current_source_key, f"external-package:{external_dir.resolve()}")
        names = [
            entry.display_name
            for entry in self.pet._discover_pet_entries()
            if entry.package is not None and entry.package.pet_id == "xiaoba"
        ]
        self.assertEqual(names, ["小八", "小八-2"])

    def test_persisting_new_source_clears_old_manual_package_history(self):
        self.settings.setValue("pet/manual_package_dirs", '["C:/stale"]')
        gif_path = self.pet.current_gif

        self.assertIsNotNone(gif_path)
        self.pet._load_gif(gif_path)

        self.assertIsNone(self.settings.value("pet/manual_package_dirs"))

    def test_todo_quick_panel_only_opens_from_badge_click(self):
        store = TodoStore(Path(self.temp_dir.name) / "todo.sqlite3")
        calendar = HolidayCalendar(
            user_path=Path(self.temp_dir.name) / "calendar.json",
            bundle_path=ROOT / "calendar_data" / "cn_workdays.json",
        )
        self.pet.close()
        self.pet = DesktopPet(
            settings=self.settings,
            todo_store=store,
            holiday_calendar=calendar,
            enable_todos=True,
        )
        self.pet.show()
        self.pet.move(120, 120)
        self.app.processEvents()
        self.pet.todo_scheduler.stop()
        self.pet.set_todo_badge_count(1)
        self.app.processEvents()

        badge_center = self.pet.todo_badge.geometry().center()
        self.pet._update_cursor_for_position(badge_center)

        self.assertEqual(self.pet.cursor().shape(), Qt.PointingHandCursor)

        QTest.mouseClick(self.pet, Qt.LeftButton, pos=self.pet.rect().center())
        self.app.processEvents()

        self.assertTrue(
            self.pet.todo_quick_panel is None
            or not self.pet.todo_quick_panel.isVisible()
        )

        QTest.mouseClick(self.pet, Qt.LeftButton, pos=badge_center)
        self.app.processEvents()

        self.assertIsNotNone(self.pet.todo_quick_panel)
        self.assertTrue(self.pet.todo_quick_panel.isVisible())

        panel_pos = self.pet.todo_quick_panel.pos()
        delta = QPoint(30, 20)
        self.pet.move(self.pet.pos() + delta)
        self.app.processEvents()

        self.assertEqual(self.pet.todo_quick_panel.pos(), panel_pos + delta)

    def test_external_todo_change_refreshes_badge_immediately(self):
        store = TodoStore(Path(self.temp_dir.name) / "todo.sqlite3")
        calendar = HolidayCalendar(
            user_path=Path(self.temp_dir.name) / "calendar.json",
            bundle_path=ROOT / "calendar_data" / "cn_workdays.json",
        )
        self.pet.close()
        self.pet = DesktopPet(
            settings=self.settings,
            todo_store=store,
            holiday_calendar=calendar,
            enable_todos=True,
        )
        self.pet.show()
        self.app.processEvents()
        self.pet.todo_scheduler.stop()

        store.add_todo(
            "外部实例新增",
            "",
            local_now().date(),
            None,
            work_calendar=calendar,
        )
        self.pet._external_todo_data_changed(TODO_CHANGE_KIND)
        self.app.processEvents()

        self.assertTrue(self.pet.todo_badge.isVisible())
        self.assertEqual(self.pet.todo_badge.text(), "1")


if __name__ == "__main__":
    unittest.main()
