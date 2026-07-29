from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional


RECURRENCE_NONE = "none"
RECURRENCE_DAILY = "daily"
RECURRENCE_WEEKLY = "weekly"
RECURRENCE_MONTHLY = "monthly"
RECURRENCE_YEARLY = "yearly"
RECURRENCE_EVERY_N_DAYS = "every_n_days"

RECURRENCE_CHOICES = (
    RECURRENCE_NONE,
    RECURRENCE_DAILY,
    RECURRENCE_WEEKLY,
    RECURRENCE_MONTHLY,
    RECURRENCE_YEARLY,
    RECURRENCE_EVERY_N_DAYS,
)

STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"
STATUS_DELETED = "deleted"

STATUS_CHOICES = (STATUS_PENDING, STATUS_COMPLETED, STATUS_DELETED)


def local_now() -> datetime:
    return datetime.now().replace(microsecond=0)


def date_to_text(value: date) -> str:
    return value.isoformat()


def optional_date_to_text(value: Optional[date]) -> str:
    if value is None:
        return ""
    return date_to_text(value)


def time_to_text(value: Optional[time]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%H:%M")


def datetime_to_text(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat(timespec="seconds")


def text_to_date(value: str) -> date:
    return date.fromisoformat(value)


def text_to_optional_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return text_to_date(value)


def text_to_time(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    return time.fromisoformat(value[:5])


def text_to_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


def normalize_recurrence(value: str) -> str:
    if value not in RECURRENCE_CHOICES:
        return RECURRENCE_NONE
    return value


@dataclass(frozen=True)
class TodoSeries:
    id: int
    title: str
    note: str
    start_date: Optional[date]
    due_time: Optional[time]
    recurrence: str
    interval_days: int
    skip_holidays: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]

    @property
    def is_recurring(self) -> bool:
        return self.recurrence != RECURRENCE_NONE


@dataclass(frozen=True)
class TodoOccurrence:
    id: int
    series_id: int
    title: str
    note: str
    due_date: Optional[date]
    due_time: Optional[time]
    status: str
    completed_at: Optional[datetime]
    notified_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    is_override: bool
    recurrence: str
    interval_days: int
    skip_holidays: bool
    series_deleted_at: Optional[datetime]

    @property
    def is_recurring(self) -> bool:
        return self.recurrence != RECURRENCE_NONE

    @property
    def has_time(self) -> bool:
        return self.due_time is not None

    @property
    def has_date(self) -> bool:
        return self.due_date is not None

    @property
    def due_sort_key(self) -> tuple[str, str]:
        date_text = date_to_text(self.due_date) if self.due_date is not None else "9999-12-31"
        return (date_text, time_to_text(self.due_time) or "99:99")

