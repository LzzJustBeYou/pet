from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal


TODO_CHANGE_KIND = "todo"
CALENDAR_CHANGE_KIND = "calendar"
CHANGE_KINDS = {TODO_CHANGE_KIND, CALENDAR_CHANGE_KIND}


def signal_path_for_database(db_path: Path | str) -> Path:
    return Path(db_path).with_name("todo_changed.signal")


class TodoChangeNotifier(QObject):
    changed = pyqtSignal(str)

    def __init__(
        self,
        signal_path: Path | str,
        parent: Optional[QObject] = None,
        debounce_ms: int = 80,
    ):
        super().__init__(parent)
        self.signal_path = Path(signal_path)
        self.debounce_ms = max(0, int(debounce_ms))
        self._pending_kind = TODO_CHANGE_KIND
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_watched_path_changed)
        self._watcher.directoryChanged.connect(self._on_watched_path_changed)
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emit_pending_change)
        self._ensure_signal_file()
        self._ensure_watches()

    def notify_change(self, kind: str = TODO_CHANGE_KIND) -> None:
        kind = self._normalize_kind(kind)
        self.signal_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": kind,
            "pid": os.getpid(),
            "timestamp_ns": time.time_ns(),
        }
        self.signal_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        self._ensure_watches()

    def stop(self) -> None:
        self._debounce_timer.stop()
        watched_paths = [*self._watcher.files(), *self._watcher.directories()]
        if watched_paths:
            self._watcher.removePaths(watched_paths)

    def _on_watched_path_changed(self, _path: str) -> None:
        self._ensure_signal_file()
        self._ensure_watches()
        kind = self._read_kind()
        if kind == CALENDAR_CHANGE_KIND:
            self._pending_kind = CALENDAR_CHANGE_KIND
        elif self._pending_kind != CALENDAR_CHANGE_KIND:
            self._pending_kind = TODO_CHANGE_KIND
        self._debounce_timer.start(self.debounce_ms)

    def _emit_pending_change(self) -> None:
        kind = self._pending_kind
        self._pending_kind = TODO_CHANGE_KIND
        self.changed.emit(kind)

    def _read_kind(self) -> str:
        try:
            payload = json.loads(self.signal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return TODO_CHANGE_KIND
        return self._normalize_kind(str(payload.get("kind", TODO_CHANGE_KIND)))

    def _ensure_signal_file(self) -> None:
        self.signal_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.signal_path.exists():
            self.signal_path.write_text("", encoding="utf-8")

    def _ensure_watches(self) -> None:
        watched_files = set(self._watcher.files())
        watched_dirs = set(self._watcher.directories())
        signal_file = str(self.signal_path)
        signal_dir = str(self.signal_path.parent)
        if signal_file not in watched_files and self.signal_path.exists():
            self._watcher.addPath(signal_file)
        if signal_dir not in watched_dirs and self.signal_path.parent.exists():
            self._watcher.addPath(signal_dir)

    def _normalize_kind(self, kind: str) -> str:
        return kind if kind in CHANGE_KINDS else TODO_CHANGE_KIND
