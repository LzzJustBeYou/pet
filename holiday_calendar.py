from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

try:
    from PyQt5.QtCore import QStandardPaths
except ImportError:  # pragma: no cover - exercised only when PyQt5 is absent.
    QStandardPaths = None


DEFAULT_CALENDAR_UPDATE_URL = (
    "https://raw.githubusercontent.com/LzzJustBeYou/pet/main/"
    "calendar_data/cn_workdays.json"
)
DEFAULT_CALENDAR_UPDATE_URLS = (
    DEFAULT_CALENDAR_UPDATE_URL,
    "https://cdn.jsdelivr.net/gh/LzzJustBeYou/pet@main/calendar_data/cn_workdays.json",
)


class CalendarDataError(ValueError):
    pass


@dataclass(frozen=True)
class WorkCalendarData:
    version: str
    region: str
    covered_start: date
    covered_end: date
    holidays: frozenset[date]
    extra_workdays: frozenset[date]
    source: str
    update_url: str
    update_urls: tuple[str, ...]


def _app_data_dir() -> Path:
    if QStandardPaths is not None:
        location = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        if location:
            return Path(location)
    return Path.home() / ".desktop_pet"


def user_calendar_path() -> Path:
    return _app_data_dir() / "calendar" / "cn_workdays.json"


def bundled_calendar_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "calendar_data" / "cn_workdays.json"


def _parse_dates(values: Iterable[str], field_name: str) -> frozenset[date]:
    parsed = set()
    for value in values:
        try:
            parsed.add(date.fromisoformat(value))
        except (TypeError, ValueError) as exc:
            raise CalendarDataError(f"{field_name} contains invalid date: {value}") from exc
    return frozenset(parsed)


def validate_calendar_payload(payload: bytes | str) -> WorkCalendarData:
    try:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalendarDataError("calendar json cannot be decoded") from exc

    try:
        version = str(data["version"])
        region = str(data.get("region", "CN"))
        covered_start = date.fromisoformat(data["covered_start"])
        covered_end = date.fromisoformat(data["covered_end"])
        holidays = _parse_dates(data.get("holidays", []), "holidays")
        extra_workdays = _parse_dates(data.get("extra_workdays", []), "extra_workdays")
        source = str(data.get("source", ""))
        update_url = str(data.get("update_url", DEFAULT_CALENDAR_UPDATE_URL))
        raw_update_urls = data.get("update_urls", DEFAULT_CALENDAR_UPDATE_URLS)
    except KeyError as exc:
        raise CalendarDataError(f"calendar json is missing {exc.args[0]}") from exc
    except ValueError as exc:
        raise CalendarDataError("calendar coverage dates are invalid") from exc

    if covered_end < covered_start:
        raise CalendarDataError("calendar coverage end is before start")
    if holidays & extra_workdays:
        raise CalendarDataError("holiday and extra workday dates overlap")

    for value in holidays | extra_workdays:
        if value < covered_start or value > covered_end:
            raise CalendarDataError(f"calendar date outside coverage: {value}")

    if isinstance(raw_update_urls, str):
        raw_update_url_values = [raw_update_urls]
    elif isinstance(raw_update_urls, (list, tuple)):
        raw_update_url_values = raw_update_urls
    else:
        raw_update_url_values = []

    update_urls = []
    for value in (update_url, *raw_update_url_values):
        if isinstance(value, str) and value.strip() and value not in update_urls:
            update_urls.append(value.strip())
    if not update_urls:
        update_urls = list(DEFAULT_CALENDAR_UPDATE_URLS)

    return WorkCalendarData(
        version=version,
        region=region,
        covered_start=covered_start,
        covered_end=covered_end,
        holidays=holidays,
        extra_workdays=extra_workdays,
        source=source,
        update_url=update_urls[0],
        update_urls=tuple(update_urls),
    )


def save_user_calendar(payload: bytes | str, path: Optional[Path] = None) -> WorkCalendarData:
    data = validate_calendar_payload(payload)
    target = path or user_calendar_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    temp_path = target.with_suffix(target.suffix + ".tmp")
    temp_path.write_text(raw, encoding="utf-8")
    os.replace(temp_path, target)
    return data


class HolidayCalendar:
    def __init__(
        self,
        user_path: Optional[Path] = None,
        bundle_path: Optional[Path] = None,
    ):
        self.user_path = user_path or user_calendar_path()
        self.bundle_path = bundle_path or bundled_calendar_path()
        self.data: Optional[WorkCalendarData] = None
        self.loaded_path: Optional[Path] = None
        self.load_error: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        self.data = None
        self.loaded_path = None
        self.load_error = None
        errors = []
        for path in (self.user_path, self.bundle_path):
            if not path.exists():
                continue
            try:
                self.data = validate_calendar_payload(path.read_text(encoding="utf-8"))
                self.loaded_path = path
                return
            except (OSError, CalendarDataError) as exc:
                errors.append(f"{path}: {exc}")
        if errors:
            self.load_error = "; ".join(errors)
        else:
            self.load_error = "no calendar data found"

    @property
    def is_available(self) -> bool:
        return self.data is not None

    @property
    def covered_start(self) -> Optional[date]:
        return self.data.covered_start if self.data else None

    @property
    def covered_end(self) -> Optional[date]:
        return self.data.covered_end if self.data else None

    @property
    def update_url(self) -> str:
        return self.data.update_url if self.data else DEFAULT_CALENDAR_UPDATE_URL

    @property
    def update_urls(self) -> tuple[str, ...]:
        return self.data.update_urls if self.data else DEFAULT_CALENDAR_UPDATE_URLS

    def status_text(self) -> str:
        if not self.data:
            return "日历未加载"
        return f"{self.data.region} {self.data.version}，覆盖至 {self.data.covered_end.isoformat()}"

    def is_covered(self, value: date) -> bool:
        return bool(
            self.data
            and self.data.covered_start <= value <= self.data.covered_end
        )

    def is_workday(self, value: date) -> bool:
        if not self.is_covered(value):
            return False
        assert self.data is not None
        if value in self.data.extra_workdays:
            return True
        if value in self.data.holidays:
            return False
        return value.weekday() < 5

    def next_workday_on_or_after(self, value: date) -> Optional[date]:
        if not self.data or value > self.data.covered_end:
            return None
        current = max(value, self.data.covered_start)
        while current <= self.data.covered_end:
            if self.is_workday(current):
                return current
            current += timedelta(days=1)
        return None

    def add_workdays(self, value: date, count: int) -> Optional[date]:
        if count < 0:
            raise ValueError("count must be non-negative")
        current = value
        remaining = count
        while remaining > 0:
            current += timedelta(days=1)
            if not self.is_covered(current):
                return None
            if self.is_workday(current):
                remaining -= 1
        return current
