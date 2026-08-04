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

    ACTIVITY_STATES = ("running", "review", "waiting")
    REACTION_STATES = ("jumping", "waving", "failed")

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
        self._active_activities = set()
        self._movement_direction: Optional[str] = None
        self._reaction_state: Optional[str] = None
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
        self._reaction_state = None
        self._recent_dx.clear()
        if interactive:
            self._update_animation(force=True)

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

        if direction != self.drag_direction:
            if direction is not None:
                self._reaction_state = None
            self.drag_direction = direction
            self._update_animation()
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
            self._update_animation()
            return "drag"

        return "click"

    def set_movement_direction(self, direction: Optional[str]) -> None:
        """Set the shared animation state for dragged and automatic movement."""
        if direction not in (None, "left", "right"):
            raise ValueError(f"unsupported movement direction: {direction}")
        if direction == self._movement_direction:
            return
        self._movement_direction = direction
        if direction is not None:
            self._reaction_state = None
        self._update_animation()

    def set_activity_active(self, state: str, active: bool) -> None:
        if state not in self.ACTIVITY_STATES:
            raise ValueError(f"unsupported activity state: {state}")
        changed = False
        if active and state not in self._active_activities:
            self._active_activities.add(state)
            changed = True
        elif not active and state in self._active_activities:
            self._active_activities.remove(state)
            changed = True
        if not changed:
            return
        if active and state in ("running", "review"):
            self._reaction_state = None
        self._update_animation()

    def trigger_reaction(self, state: str) -> bool:
        if state not in self.REACTION_STATES:
            raise ValueError(f"unsupported reaction state: {state}")
        if not self.interactive or self.dragging or self._movement_direction is not None:
            return False
        if "running" in self._active_activities or "review" in self._active_activities:
            return False
        self._reaction_state = state
        self._update_animation()
        return True

    def animation_finished(self, state: str) -> None:
        if state != self.current_state or state != self._reaction_state:
            return
        self._reaction_state = None
        self._update_animation()

    def _trigger_hover(self) -> None:
        if not self.interactive or not self.cursor_inside or self.pressed:
            return
        self.hover_consumed = True
        if self._effective_state() != "idle":
            return
        self.trigger_reaction("jumping")

    def _effective_state(self) -> str:
        if self.dragging and self.drag_direction is not None:
            return f"running-{self.drag_direction}"
        for state in self.ACTIVITY_STATES[:2]:
            if state in self._active_activities:
                return state
        if self._movement_direction is not None:
            return f"running-{self._movement_direction}"
        if self._reaction_state is not None:
            return self._reaction_state
        if "waiting" in self._active_activities:
            return "waiting"
        return "idle"

    def _update_animation(self, force: bool = False) -> None:
        state = self._effective_state()
        if not force and state == self.current_state:
            return
        self.current_state = state
        if self.interactive:
            self.animation_requested.emit(state, state not in self.REACTION_STATES)
