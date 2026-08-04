from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QObject, QTimer


WALK_INTERVAL_MS = 30
WALK_STEP_PIXELS = 2


@dataclass(frozen=True)
class WalkingStep:
    x: int
    direction: str


class WalkingController(QObject):
    """Owns walking state, timer lifecycle, and horizontal edge reversal."""

    def __init__(
        self,
        parent: Optional[QObject] = None,
        interval_ms: int = WALK_INTERVAL_MS,
        step_pixels: int = WALK_STEP_PIXELS,
    ):
        super().__init__(parent)
        self.enabled = False
        self.direction = "right"
        self.step_pixels = max(1, int(step_pixels))
        self.timer = QTimer(self)
        self.timer.setInterval(max(1, int(interval_ms)))

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def set_direction(self, direction: str) -> None:
        self.direction = "left" if direction == "left" else "right"

    def align_direction(self, current_x: int, bounds: Optional[tuple[int, int]]) -> str:
        if bounds is not None:
            minimum_x, maximum_x = bounds
            if current_x >= maximum_x:
                self.direction = "left"
            elif current_x <= minimum_x:
                self.direction = "right"
        return self.direction

    def sync_timer(self, can_walk: bool) -> None:
        if can_walk:
            self.timer.start()
        else:
            self.timer.stop()

    def advance(
        self,
        current_x: int,
        bounds: Optional[tuple[int, int]],
    ) -> Optional[WalkingStep]:
        if bounds is None:
            return None
        minimum_x, maximum_x = bounds
        delta = self.step_pixels if self.direction == "right" else -self.step_pixels
        target_x = current_x + delta
        if target_x >= maximum_x:
            target_x = maximum_x
            self.direction = "left"
        elif target_x <= minimum_x:
            target_x = minimum_x
            self.direction = "right"
        return WalkingStep(target_x, self.direction)
