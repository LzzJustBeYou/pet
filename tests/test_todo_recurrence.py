import unittest
from datetime import date, time
from pathlib import Path

from holiday_calendar import HolidayCalendar
from todo_models import (
    RECURRENCE_DAILY,
    RECURRENCE_EVERY_N_DAYS,
    RECURRENCE_MONTHLY,
    RECURRENCE_WEEKLY,
    RECURRENCE_YEARLY,
    TodoSeries,
    local_now,
)
from todo_recurrence import occurrence_dates_until


ROOT = Path(__file__).resolve().parents[1]


def make_series(start_date, recurrence, interval_days=1, skip_holidays=False):
    now = local_now()
    return TodoSeries(
        id=1,
        title="test",
        note="",
        start_date=start_date,
        due_time=time(9, 0),
        recurrence=recurrence,
        interval_days=interval_days,
        skip_holidays=skip_holidays,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


class TodoRecurrenceTests(unittest.TestCase):
    def setUp(self):
        self.calendar = HolidayCalendar(
            user_path=ROOT / "missing-user-calendar.json",
            bundle_path=ROOT / "calendar_data" / "cn_workdays.json",
        )

    def test_monthly_recurrence_clamps_to_month_end_without_losing_anchor(self):
        series = make_series(date(2026, 1, 31), RECURRENCE_MONTHLY)

        dates = occurrence_dates_until(series, date(2026, 3, 1), self.calendar)

        self.assertEqual(
            dates,
            [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)],
        )

    def test_yearly_feb_29_clamps_on_non_leap_year(self):
        series = make_series(date(2024, 2, 29), RECURRENCE_YEARLY)

        dates = occurrence_dates_until(series, date(2025, 1, 1), self.calendar)

        self.assertEqual(dates, [date(2024, 2, 29), date(2025, 2, 28)])

    def test_weekly_skip_holidays_moves_occurrence_forward_only(self):
        series = make_series(date(2026, 10, 3), RECURRENCE_WEEKLY, skip_holidays=True)

        dates = occurrence_dates_until(series, date(2026, 10, 3), self.calendar)

        self.assertEqual(dates, [date(2026, 10, 8)])

    def test_every_n_days_with_skip_holidays_counts_workdays(self):
        series = make_series(
            date(2026, 9, 18),
            RECURRENCE_EVERY_N_DAYS,
            interval_days=2,
            skip_holidays=True,
        )

        dates = occurrence_dates_until(series, date(2026, 9, 21), self.calendar)

        self.assertEqual(
            dates,
            [date(2026, 9, 18), date(2026, 9, 21), date(2026, 9, 23)],
        )

    def test_skip_holiday_recurrence_stops_at_calendar_boundary(self):
        series = make_series(date(2026, 12, 31), RECURRENCE_DAILY, skip_holidays=True)

        dates = occurrence_dates_until(series, date(2026, 12, 31), self.calendar)

        self.assertEqual(dates, [date(2026, 12, 31)])


if __name__ == "__main__":
    unittest.main()

