from __future__ import annotations

import sys
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from holiday_calendar import HolidayCalendar
from todo_models import TodoOccurrence, local_now
from todo_store import TodoStore


class TodoScheduler(QObject):
    badge_count_changed = pyqtSignal(int)
    reminders_claimed = pyqtSignal(object)

    def __init__(
        self,
        store: TodoStore,
        work_calendar: HolidayCalendar,
        parent=None,
        interval_ms: int = 15000,
    ):
        super().__init__(parent)
        self.store = store
        self.work_calendar = work_calendar
        self.interval_ms = interval_ms
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_now)

    def start(self) -> None:
        self.check_now()
        self._timer.start(self.interval_ms)

    def stop(self) -> None:
        self._timer.stop()

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
