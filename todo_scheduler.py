from __future__ import annotations

import sys
from datetime import datetime, timedelta

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from holiday_calendar import HolidayCalendar
from todo_models import local_now
from todo_store import TodoStore


DEFAULT_POLL_STEP_MINUTES = 5
DEFAULT_POLL_INTERVAL_MS = DEFAULT_POLL_STEP_MINUTES * 60 * 1000


def milliseconds_until_next_step(
    now: datetime,
    step_minutes: int = DEFAULT_POLL_STEP_MINUTES,
) -> int:
    step_minutes = max(1, min(60, int(step_minutes)))
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_minutes = now.hour * 60 + now.minute
    next_step_minute = ((elapsed_minutes // step_minutes) + 1) * step_minutes
    if next_step_minute >= 24 * 60:
        target = day_start + timedelta(days=1)
    else:
        target = day_start + timedelta(minutes=next_step_minute)
    return max(1, int((target - now).total_seconds() * 1000))


class TodoScheduler(QObject):
    badge_count_changed = pyqtSignal(int)
    reminders_claimed = pyqtSignal(object)

    def __init__(
        self,
        store: TodoStore,
        work_calendar: HolidayCalendar,
        parent=None,
        poll_step_minutes: int = DEFAULT_POLL_STEP_MINUTES,
    ):
        super().__init__(parent)
        self.store = store
        self.work_calendar = work_calendar
        self.poll_step_minutes = max(1, min(60, int(poll_step_minutes)))
        self.interval_ms = self.poll_step_minutes * 60 * 1000
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)

    def start(self) -> None:
        self.check_now()
        self._schedule_next_check()

    def stop(self) -> None:
        self._timer.stop()

    def _on_timer(self) -> None:
        self.check_now()
        self._schedule_next_check()

    def _schedule_next_check(self) -> None:
        self._timer.start(
            milliseconds_until_next_step(local_now(), self.poll_step_minutes)
        )

    def check_now(self) -> None:
        try:
            now = local_now()
            claimed = self.store.claim_due_reminders(now, self.work_calendar)
            count = self.store.reminder_count(now, self.work_calendar)
        except Exception as exc:
            print(f"[TodoScheduler] check failed: {exc}", file=sys.stderr)
            return
        self.badge_count_changed.emit(count)
        if claimed:
            self.reminders_claimed.emit(claimed)

    def refresh_badge(self, now: datetime | None = None) -> None:
        try:
            count = self.store.reminder_count(now or local_now(), self.work_calendar)
        except Exception as exc:
            print(f"[TodoScheduler] badge refresh failed: {exc}", file=sys.stderr)
            return
        self.badge_count_changed.emit(count)
