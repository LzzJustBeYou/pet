import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from main import DesktopPet


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


if __name__ == "__main__":
    unittest.main()
