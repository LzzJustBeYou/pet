from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pet_package import (
    PetPackage,
    PetPackageError,
    canonical_path,
    find_pet_directories,
    load_pet_package,
)


def resource_path(relative_path) -> str:
    """Return a resource path in development and PyInstaller builds."""
    base_path = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return os.path.join(str(base_path), relative_path)


def scan_actions(actions_dir="actions"):
    """Return GIF actions grouped by their immediate parent directory."""
    categories = []
    target_dir = resource_path(actions_dir)
    if not os.path.isdir(target_dir):
        return categories

    for category in sorted(os.listdir(target_dir)):
        category_path = os.path.join(target_dir, category)
        if not os.path.isdir(category_path):
            continue
        actions = []
        for filename in sorted(os.listdir(category_path)):
            if filename.lower().endswith(".gif"):
                actions.append(
                    (
                        os.path.splitext(filename)[0],
                        os.path.join(category_path, filename),
                    )
                )
        if actions:
            categories.append((category, actions))
    return categories


@dataclass
class PetMenuEntry:
    package_dir: Path
    source_key: str
    origin: str
    package: Optional[PetPackage] = None
    error: Optional[str] = None
    runtime_id: str = ""
    display_name: str = ""


class PetCatalog:
    """Discovers pet packages and translates persisted resource keys."""

    def __init__(self, actions_root=None, builtin_root=None):
        self.actions_root = Path(actions_root or resource_path("actions")).resolve()
        self.builtin_root = Path(builtin_root or resource_path("pets")).resolve()

    def gif_key(self, gif_path: str) -> str:
        resolved = Path(gif_path).resolve()
        try:
            relative = resolved.relative_to(self.actions_root)
            return f"builtin-gif:{relative.as_posix()}"
        except ValueError:
            return f"external-gif:{resolved}"

    def resolve_gif_key(self, key: str) -> Optional[str]:
        if key.startswith("builtin-gif:"):
            relative = key.split(":", 1)[1]
            return str(self.actions_root / Path(relative))
        if key.startswith("external-gif:"):
            return key.split(":", 1)[1]
        return key or None

    @staticmethod
    def external_package_dir_from_key(source_key: Optional[str]) -> Optional[Path]:
        if source_key and source_key.startswith("external-package:"):
            return Path(source_key.split(":", 1)[1])
        return None

    def entry_from_key(self, source_key: str) -> Optional[PetMenuEntry]:
        if source_key.startswith("builtin-package:"):
            relative = source_key.split(":", 1)[1]
            return self.entry_for_dir(
                self.builtin_root / Path(relative),
                "builtin",
                self.builtin_root,
            )
        external_dir = self.external_package_dir_from_key(source_key)
        if external_dir is not None:
            return self.entry_for_dir(external_dir, "local", self.builtin_root)
        return None

    def entry_for_dir(
        self,
        raw_path,
        origin: str,
        builtin_root: Optional[Path] = None,
    ) -> PetMenuEntry:
        package_dir = Path(raw_path).expanduser().resolve()
        root = Path(builtin_root or self.builtin_root).resolve()
        if origin == "builtin":
            try:
                relative = package_dir.relative_to(root).as_posix()
            except ValueError:
                relative = package_dir.name
            source_key = f"builtin-package:{relative}"
        else:
            source_key = f"external-package:{package_dir}"

        try:
            package = load_pet_package(package_dir)
            return PetMenuEntry(
                package_dir=package_dir,
                source_key=source_key,
                origin=origin,
                package=package,
            )
        except PetPackageError as exc:
            return PetMenuEntry(
                package_dir=package_dir,
                source_key=source_key,
                origin=origin,
                error=str(exc),
                display_name=f"{package_dir.name}（不可用）",
            )

    def discover_entries(
        self,
        current_source_type: Optional[str] = None,
        current_source_key: Optional[str] = None,
    ) -> list[PetMenuEntry]:
        entries: list[PetMenuEntry] = []
        seen_paths = set()
        candidates = [(path, "builtin") for path in find_pet_directories(self.builtin_root)]

        current_external_dir = self.external_package_dir_from_key(
            current_source_key if current_source_type == "package" else None
        )
        if current_external_dir is not None:
            candidates.append((current_external_dir, "local"))

        for raw_path, origin in candidates:
            path_key = canonical_path(raw_path)
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            entry = self.entry_for_dir(raw_path, origin, self.builtin_root)
            if entry.package is None and origin == "builtin":
                print(
                    f"[DesktopPet] skipped invalid pet {entry.package_dir}: {entry.error}",
                    file=sys.stderr,
                )
                continue
            entries.append(entry)

        duplicate_counts = {}
        for entry in entries:
            if entry.package is None:
                continue
            pet_id = entry.package.pet_id
            count = duplicate_counts.get(pet_id, 0) + 1
            duplicate_counts[pet_id] = count
            suffix = "" if count == 1 else f"-{count}"
            entry.runtime_id = f"{pet_id}{suffix}"
            entry.display_name = f"{entry.package.display_name}{suffix}"
        return entries
