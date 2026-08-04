"""Compatibility exports for the split todo UI components.

The concrete widgets live in focused modules; this module keeps the original
import surface stable for the application and third-party integrations.
"""

from todo_models import (
    RECURRENCE_DAILY,
    RECURRENCE_EVERY_N_DAYS,
    RECURRENCE_MONTHLY,
    RECURRENCE_NONE,
    RECURRENCE_WEEKLY,
    RECURRENCE_YEARLY,
    STATUS_COMPLETED,
    TodoOccurrence,
    local_now,
    time_to_text,
)
from todo_store import TodoStore, TodoValidationError
from todo_ui_common import (
    RECURRENCE_ITEMS,
    TIME_STEP_MINUTES,
    SteppedTimeEdit,
    calendar_errors_are_not_found,
    from_qdate,
    from_qtime,
    occurrence_is_due_at,
    snap_time_to_step,
    to_qdate,
    to_qtime,
)
from todo_manager_window import TodoManagerWindow
from todo_quick_panel import TodoQuickPanel
from todo_reminder_bubble import TodoReminderBubble

# Keep the old private helper names importable for existing integrations.
_to_qdate = to_qdate
_from_qdate = from_qdate
_to_qtime = to_qtime
_from_qtime = from_qtime

__all__ = [
    "TodoManagerWindow",
    "TodoQuickPanel",
    "TodoReminderBubble",
    "SteppedTimeEdit",
    "RECURRENCE_ITEMS",
    "TIME_STEP_MINUTES",
    "calendar_errors_are_not_found",
    "occurrence_is_due_at",
    "snap_time_to_step",
    "to_qdate",
    "from_qdate",
    "to_qtime",
    "from_qtime",
    "_to_qdate",
    "_from_qdate",
    "_to_qtime",
    "_from_qtime",
]
