from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from PyQt5.QtCore import QObject, QPoint, QTimer, pyqtSignal


@dataclass(frozen=True)
class DragUpdate:
    dragging: bool
    started: bool
    direction: Optional[str]


class PetInteractionController(QObject):
    animation_requested = pyqtSignal(str, bool)

    def __init__(
        self,
        parent=None,
        hover_delay_ms: int = 150,
        drag_distance: int = 6,
        direction_deadzone: int = 2,
    ):
        super().__init__(parent)
        self.hover_delay_ms = hover_delay_ms
        self.drag_distance = drag_distance
        self.direction_deadzone = direction_deadzone
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._trigger_hover)
        self.interactive = False
        self.cursor_inside = False
        self.hover_consumed = False
        self.pressed = False
        self.dragging = False
        self.current_state = "idle"
        self.press_position = QPoint()
        self.last_position = QPoint()
        self.drag_direction: Optional[str] = None
        self._recent_dx: Deque[int] = deque(maxlen=4)

    def activate(self, interactive: bool) -> None:
        self._hover_timer.stop()
        self.interactive = interactive
        self.cursor_inside = False
        self.hover_consumed = False
        self.pressed = False
        self.dragging = False
        self.current_state = "idle"
        self.drag_direction = None
        self._recent_dx.clear()
        if interactive:
            self.animation_requested.emit("idle", True)

    def pointer_enter(self) -> None:
        if self.cursor_inside:
            return
        self.cursor_inside = True
        if self.interactive and not self.hover_consumed and not self.pressed:
            self._hover_timer.start(self.hover_delay_ms)

    def pointer_leave(self) -> None:
        if not self.cursor_inside:
            return
        self.cursor_inside = False
        self.hover_consumed = False
        self._hover_timer.stop()

    def press(self, global_position: QPoint) -> None:
        self._hover_timer.stop()
        self.pressed = True
        self.dragging = False
        self.press_position = QPoint(global_position)
        self.last_position = QPoint(global_position)
        self.drag_direction = None
        self._recent_dx.clear()

    def move(self, global_position: QPoint) -> DragUpdate:
        if not self.pressed:
            return DragUpdate(False, False, self.drag_direction)

        step_dx = global_position.x() - self.last_position.x()
        self.last_position = QPoint(global_position)
        self._recent_dx.append(step_dx)

        delta = global_position - self.press_position
        started = False
        if not self.dragging:
            distance_squared = delta.x() * delta.x() + delta.y() * delta.y()
            if distance_squared > self.drag_distance * self.drag_distance:
                self.dragging = True
                started = True
                self.hover_consumed = True

        if not self.dragging:
            return DragUpdate(False, False, self.drag_direction)

        smoothed_dx = sum(self._recent_dx)
        direction = self.drag_direction
        if smoothed_dx >= self.direction_deadzone:
            direction = "right"
        elif smoothed_dx <= -self.direction_deadzone:
            direction = "left"

        if started and direction is None:
            self.current_state = "idle"
            self.animation_requested.emit("idle", True)
        elif direction != self.drag_direction and direction is not None:
            self.current_state = f"running-{direction}"
            self.animation_requested.emit(self.current_state, True)
        self.drag_direction = direction
        return DragUpdate(True, started, direction)

    def release(self) -> str:
        if not self.pressed:
            return "none"
        self.pressed = False

        if self.dragging:
            self.dragging = False
            self.drag_direction = None
            self._recent_dx.clear()
            self.hover_consumed = True
            self.current_state = "idle"
            if self.interactive:
                self.animation_requested.emit("idle", True)
            return "drag"

        return "click"

    def animation_finished(self, state: str) -> None:
        if self.dragging or state != self.current_state:
            return
        if state in ("jumping", "waving"):
            self.current_state = "idle"
            self.animation_requested.emit("idle", True)

    def _trigger_hover(self) -> None:
        if not self.interactive or not self.cursor_inside or self.pressed:
            return
        self.hover_consumed = True
        if self.current_state != "idle":
            return
        self.current_state = "jumping"
        self.animation_requested.emit("jumping", False)
