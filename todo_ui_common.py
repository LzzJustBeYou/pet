from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from PyQt5.QtCore import QDate, QTime
from PyQt5.QtWidgets import QTimeEdit

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
)


RECURRENCE_ITEMS = [
    ("不重复", RECURRENCE_NONE),
    ("每天", RECURRENCE_DAILY),
    ("每周", RECURRENCE_WEEKLY),
    ("每月", RECURRENCE_MONTHLY),
    ("每年", RECURRENCE_YEARLY),
    ("每 N 天", RECURRENCE_EVERY_N_DAYS),
]
TIME_STEP_MINUTES = 5


def to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def from_qdate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def to_qtime(value: Optional[time]) -> QTime:
    if value is None:
        now = local_now()
        value = snap_time_to_step(time(now.hour, now.minute))
    return QTime(value.hour, value.minute)


def from_qtime(value: QTime) -> time:
    return time(value.hour(), value.minute())


def snap_time_to_step(
    value: time,
    step_minutes: int = TIME_STEP_MINUTES,
    round_up: bool = True,
) -> time:
    step_minutes = max(1, min(60, int(step_minutes)))
    total_minutes = value.hour * 60 + value.minute
    if total_minutes % step_minutes:
        if round_up:
            total_minutes = ((total_minutes // step_minutes) + 1) * step_minutes
        else:
            total_minutes = round(total_minutes / step_minutes) * step_minutes
    total_minutes = min(total_minutes, 23 * 60 + (60 - step_minutes))
    return time(total_minutes // 60, total_minutes % 60)


def calendar_errors_are_not_found(errors: list[str]) -> bool:
    return bool(errors) and all("not found" in error.lower() for error in errors)


def occurrence_is_due_at(occurrence: TodoOccurrence, now: datetime) -> bool:
    if occurrence.status == STATUS_COMPLETED:
        return False
    if occurrence.due_date is None:
        return False
    if occurrence.due_date < now.date():
        return True
    if occurrence.due_date > now.date():
        return False
    if occurrence.due_time is None:
        return True
    return occurrence.due_time <= now.time().replace(second=0, microsecond=0)


class SteppedTimeEdit(QTimeEdit):
    def __init__(self, parent=None, step_minutes: int = TIME_STEP_MINUTES):
        super().__init__(parent)
        self.step_minutes = step_minutes
        self.editingFinished.connect(self.snap_to_step)

    def stepBy(self, steps: int) -> None:
        current = snap_time_to_step(from_qtime(self.time()), self.step_minutes)
        total_minutes = current.hour * 60 + current.minute + steps * self.step_minutes
        total_minutes = max(0, min(23 * 60 + (60 - self.step_minutes), total_minutes))
        self.setTime(QTime(total_minutes // 60, total_minutes % 60))

    def snap_to_step(self) -> None:
        snapped = snap_time_to_step(from_qtime(self.time()), self.step_minutes)
        self.setTime(QTime(snapped.hour, snapped.minute))
