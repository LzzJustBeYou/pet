import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage, QImageReader


CELL_WIDTH = 192
CELL_HEIGHT = 208
ATLAS_COLUMNS = 8
STANDARD_ROWS = 9
EXTENDED_ROWS = 11

EXPECTED_SIZE_BY_VERSION = {
    1: QSize(CELL_WIDTH * ATLAS_COLUMNS, CELL_HEIGHT * STANDARD_ROWS),
    2: QSize(CELL_WIDTH * ATLAS_COLUMNS, CELL_HEIGHT * EXTENDED_ROWS),
}

USED_COLUMNS_BY_ROW = {
    0: 6,
    1: 8,
    2: 8,
    3: 4,
    4: 5,
    5: 8,
    6: 6,
    7: 6,
    8: 6,
    9: 8,
    10: 8,
}


class PetPackageError(ValueError):
    pass


@dataclass(frozen=True)
class PetPackage:
    package_dir: Path
    manifest_path: Path
    sprite_path: Path
    pet_id: str
    display_name: str
    description: str
    kind: Optional[str]
    sprite_version: int
    image_size: QSize


def _visible_alpha(image: QImage) -> bool:
    alpha = image.convertToFormat(QImage.Format_Alpha8)
    if alpha.isNull():
        return False
    return any(alpha.constBits().asstring(alpha.byteCount()))


def _validate_cells(image: QImage, version: int) -> None:
    row_count = STANDARD_ROWS if version == 1 else EXTENDED_ROWS
    for row in range(row_count):
        used_columns = USED_COLUMNS_BY_ROW[row]
        for column in range(ATLAS_COLUMNS):
            cell = image.copy(
                column * CELL_WIDTH,
                row * CELL_HEIGHT,
                CELL_WIDTH,
                CELL_HEIGHT,
            )
            visible = _visible_alpha(cell)
            if column < used_columns and not visible:
                raise PetPackageError(
                    f"required frame is empty: row {row}, column {column}"
                )
            if column >= used_columns and visible:
                raise PetPackageError(
                    f"unused frame must be transparent: row {row}, column {column}"
                )


def _read_manifest(manifest_path: Path) -> dict:
    try:
        with manifest_path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise PetPackageError("pet.json is missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PetPackageError(f"pet.json cannot be read: {exc}") from exc
    if not isinstance(data, dict):
        raise PetPackageError("pet.json must contain a JSON object")
    return data


def _required_text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PetPackageError(f"pet.json field '{key}' must be a non-empty string")
    return value.strip()


def _resolve_sprite_path(package_dir: Path, relative_path: str) -> Path:
    package_root = package_dir.resolve()
    sprite_path = (package_root / relative_path).resolve()
    try:
        sprite_path.relative_to(package_root)
    except ValueError as exc:
        raise PetPackageError("spritesheetPath must stay inside the pet directory") from exc
    if not sprite_path.is_file():
        raise PetPackageError(f"spritesheet is missing: {relative_path}")
    return sprite_path


def _resolve_version(data: dict, size: QSize) -> int:
    declared = data.get("spriteVersionNumber")
    if declared is not None:
        if isinstance(declared, bool) or declared not in (1, 2):
            raise PetPackageError("spriteVersionNumber must be 1 or 2")
        version = int(declared)
        if size != EXPECTED_SIZE_BY_VERSION[version]:
            expected = EXPECTED_SIZE_BY_VERSION[version]
            raise PetPackageError(
                "spritesheet dimensions do not match spriteVersionNumber: "
                f"expected {expected.width()}x{expected.height()}, "
                f"got {size.width()}x{size.height()}"
            )
        return version

    for version, expected in EXPECTED_SIZE_BY_VERSION.items():
        if size == expected:
            return version
    raise PetPackageError(
        "unsupported spritesheet dimensions: "
        f"{size.width()}x{size.height()}"
    )


def load_pet_package(path) -> PetPackage:
    package_dir = Path(path).expanduser()
    if package_dir.name.lower() == "pet.json":
        package_dir = package_dir.parent
    package_dir = package_dir.resolve()
    if not package_dir.is_dir():
        raise PetPackageError("pet directory does not exist")

    manifest_path = package_dir / "pet.json"
    data = _read_manifest(manifest_path)
    pet_id = _required_text(data, "id")
    display_name = _required_text(data, "displayName")
    relative_sprite_path = _required_text(data, "spritesheetPath")
    sprite_path = _resolve_sprite_path(package_dir, relative_sprite_path)

    reader = QImageReader(str(sprite_path))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid():
        raise PetPackageError(
            f"spritesheet cannot be decoded: {reader.errorString()}"
        )
    version = _resolve_version(data, size)
    image = reader.read()
    if image.isNull():
        raise PetPackageError(
            f"spritesheet cannot be decoded: {reader.errorString()}"
        )
    _validate_cells(image, version)

    description = data.get("description", "")
    if not isinstance(description, str):
        description = ""
    kind = data.get("kind")
    if kind is not None and not isinstance(kind, str):
        kind = None

    return PetPackage(
        package_dir=package_dir,
        manifest_path=manifest_path,
        sprite_path=sprite_path,
        pet_id=pet_id,
        display_name=display_name,
        description=description.strip(),
        kind=kind,
        sprite_version=version,
        image_size=size,
    )


def find_pet_directories(root) -> List[Path]:
    root_path = Path(root).expanduser()
    if not root_path.is_dir():
        return []
    if (root_path / "pet.json").is_file():
        return [root_path.resolve()]
    return [
        child.resolve()
        for child in sorted(root_path.iterdir(), key=lambda item: item.name.lower())
        if child.is_dir() and (child / "pet.json").is_file()
    ]


def canonical_path(path) -> str:
    return str(Path(path).expanduser().resolve()).casefold()
