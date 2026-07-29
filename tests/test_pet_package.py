import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pet_package import (
    PetPackageError,
    find_pet_directories,
    load_pet_package,
)


ROOT = Path(__file__).resolve().parents[1]
BUILTIN_PET = ROOT / "pets" / "xiaoba"


class PetPackageTests(unittest.TestCase):
    def test_loads_bundled_v1_package_by_dimensions(self):
        package = load_pet_package(BUILTIN_PET)

        self.assertEqual(package.pet_id, "xiaoba")
        self.assertEqual(package.display_name, "小八")
        self.assertEqual(package.sprite_version, 1)
        self.assertEqual((package.image_size.width(), package.image_size.height()), (1536, 1872))
        self.assertNotIn("Codex", package.description)

    def test_rejects_declared_v2_with_v1_dimensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "broken"
            package_dir.mkdir()
            shutil.copy2(BUILTIN_PET / "spritesheet.webp", package_dir / "spritesheet.webp")
            manifest = json.loads((BUILTIN_PET / "pet.json").read_text(encoding="utf-8"))
            manifest["spriteVersionNumber"] = 2
            (package_dir / "pet.json").write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(PetPackageError, "dimensions"):
                load_pet_package(package_dir)

    def test_rejects_spritesheet_path_outside_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "broken"
            package_dir.mkdir()
            shutil.copy2(BUILTIN_PET / "spritesheet.webp", root / "outside.webp")
            manifest = {
                "id": "broken",
                "displayName": "Broken",
                "spritesheetPath": "../outside.webp",
            }
            (package_dir / "pet.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(PetPackageError, "stay inside"):
                load_pet_package(package_dir)

    def test_finds_package_directories_one_level_below_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shutil.copytree(BUILTIN_PET, root / "xiaoba")
            (root / "not-a-pet").mkdir()

            self.assertEqual(find_pet_directories(root), [(root / "xiaoba").resolve()])


if __name__ == "__main__":
    unittest.main()
