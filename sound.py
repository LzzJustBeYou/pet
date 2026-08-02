"""音效管理（Health Reminder 提示音）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QObject, QUrl


SOUND_NAMES = ("complete", "remind")


def resource_base() -> str:
    return str(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


class SoundManager(QObject):
    def __init__(
        self,
        parent: Optional[QObject] = None,
        base_dir: Optional[str] = None,
        enabled_provider: Optional[Callable[[], bool]] = None,
    ):
        super().__init__(parent)
        self._base_dir = base_dir if base_dir is not None else resource_base()
        self._enabled_provider = enabled_provider or (lambda: True)
        self._effects = {}
        try:
            from PyQt5.QtMultimedia import QSoundEffect
        except Exception:
            self._effect_cls = None
        else:
            self._effect_cls = QSoundEffect
        if self._effect_cls is not None:
            for name in SOUND_NAMES:
                self._load(name)

    def _load(self, name: str) -> None:
        path = os.path.join(self._base_dir, "assets", "sounds", f"{name}.wav")
        if not os.path.isfile(path):
            return
        effect = self._effect_cls(self)
        effect.setSource(QUrl.fromLocalFile(path))
        effect.setVolume(0.8)
        self._effects[name] = effect

    def play(self, name: str) -> None:
        if not self._enabled_provider():
            return
        effect = self._effects.get(name)
        if effect is not None:
            effect.play()
