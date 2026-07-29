from __future__ import annotations

import calendar as calendar_module
from datetime import date, timedelta
from typing import Iterable, Optional

from holiday_calendar import HolidayCalendar
from todo_models import (
    RECURRENCE_DAILY,
    RECURRENCE_EVERY_N_DAYS,
    RECURRENCE_MONTHLY,
    RECURRENCE_NONE,
    RECURRENCE_WEEKLY,
    RECURRENCE_YEARLY,
    TodoSeries,
)


MAX_GENERATED_OCCURRENCES_PER_SERIES = 5000


def _clamped_date(year: int, month: int, day: int) -> date:
    last_day = calendar_module.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _add_months(anchor: date, months: int) -> date:
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    return _clamped_date(year, month, anchor.day)


def _add_years(anchor: date, years: int) -> date:
    return _clamped_date(anchor.year + years, anchor.month, anchor.day)


def _adjust_for_holidays(
    value: date,
    skip_holidays: bool,
    work_calendar: HolidayCalendar,
) -> Optional[date]:
    if not skip_holidays:
        return value
    return work_calendar.next_workday_on_or_after(value)


def occurrence_dates_until(
    series: TodoSeries,
    through_date: date,
    work_calendar: HolidayCalendar,
    include_next_future: bool = True,
) -> list[date]:
    """Return materialized dates due through through_date, plus one future date."""
    if series.start_date is None:
        return []

    values = []
    seen = set()

    def add_value(candidate: Optional[date]) -> bool:
        if candidate is None:
            return False
        if candidate not in seen:
            seen.add(candidate)
            values.append(candidate)
        return candidate <= through_date

    if series.recurrence == RECURRENCE_NONE:
        candidate = _adjust_for_holidays(
            series.start_date,
            series.skip_holidays,
            work_calendar,
        )
        if candidate is not None and (candidate <= through_date or include_next_future):
            add_value(candidate)
        return values

    if series.recurrence in (RECURRENCE_DAILY, RECURRENCE_EVERY_N_DAYS):
        interval = 1 if series.recurrence == RECURRENCE_DAILY else series.interval_days
        interval = max(1, interval)

        if series.skip_holidays:
            candidate = work_calendar.next_workday_on_or_after(series.start_date)
            generated = 0
            while candidate is not None and generated < MAX_GENERATED_OCCURRENCES_PER_SERIES:
                generated += 1
                should_continue = add_value(candidate)
                if not should_continue:
                    break
                candidate = work_calendar.add_workdays(candidate, interval)
            return values

        candidate = series.start_date
        generated = 0
        while generated < MAX_GENERATED_OCCURRENCES_PER_SERIES:
            generated += 1
            should_continue = add_value(candidate)
            if not should_continue:
                break
            candidate += timedelta(days=interval)
        return values

    generated = 0
    index = 0
    while generated < MAX_GENERATED_OCCURRENCES_PER_SERIES:
        generated += 1
        if series.recurrence == RECURRENCE_WEEKLY:
            base_date = series.start_date + timedelta(days=index * 7)
        elif series.recurrence == RECURRENCE_MONTHLY:
            base_date = _add_months(series.start_date, index)
        elif series.recurrence == RECURRENCE_YEARLY:
            base_date = _add_years(series.start_date, index)
        else:
            break

        candidate = _adjust_for_holidays(base_date, series.skip_holidays, work_calendar)
        if candidate is None:
            break
        should_continue = add_value(candidate)
        if not should_continue:
            break
        index += 1

    return values


def has_schedulable_date(
    series: TodoSeries,
    through_date: date,
    work_calendar: HolidayCalendar,
) -> bool:
    return bool(occurrence_dates_until(series, through_date, work_calendar))

