import tempfile
import unittest
from datetime import date, datetime, time
from pathlib import Path

from holiday_calendar import HolidayCalendar
from todo_models import RECURRENCE_DAILY, RECURRENCE_EVERY_N_DAYS
from todo_store import TodoStore


ROOT = Path(__file__).resolve().parents[1]


class TodoStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "todo.sqlite3"
        self.calendar = HolidayCalendar(
            user_path=Path(self.temp_dir.name) / "calendar.json",
            bundle_path=ROOT / "calendar_data" / "cn_workdays.json",
        )
        self.store = TodoStore(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_date_only_todo_counts_but_does_not_claim_reminder(self):
        today = date(2026, 7, 29)
        self.store.add_todo("买咖啡", "", today, None, work_calendar=self.calendar)

        self.assertEqual(self.store.badge_count(today, self.calendar), 1)
        self.assertEqual(
            self.store.reminder_count(datetime(2026, 7, 29, 0, 0), self.calendar),
            1,
        )
        claimed = self.store.claim_due_reminders(
            datetime(2026, 7, 29, 18, 0),
            self.calendar,
        )
        self.assertEqual(claimed, [])

    def test_timed_todo_counts_as_reminder_only_at_due_time(self):
        today = date(2026, 7, 29)
        self.store.add_todo("开会", "", today, time(15, 0), work_calendar=self.calendar)

        self.assertEqual(self.store.badge_count(today, self.calendar), 1)
        self.assertEqual(
            self.store.reminder_count(datetime(2026, 7, 29, 14, 59), self.calendar),
            0,
        )
        self.assertEqual(
            self.store.reminder_count(datetime(2026, 7, 29, 15, 0), self.calendar),
            1,
        )

    def test_recurring_occurrences_accumulate_independently(self):
        self.store.add_todo(
            "站会",
            "",
            date(2026, 7, 28),
            time(9, 0),
            recurrence=RECURRENCE_DAILY,
            work_calendar=self.calendar,
        )
        today = date(2026, 7, 29)
        occurrences = self.store.list_today(today, self.calendar)

        self.assertEqual([item.due_date for item in occurrences], [date(2026, 7, 28), today])
        self.store.complete_occurrence(occurrences[0].id)
        self.assertEqual(self.store.badge_count(today, self.calendar), 1)

    def test_every_n_workday_recurrence_uses_shared_calendar(self):
        self.store.add_todo(
            "复盘",
            "",
            date(2026, 9, 18),
            time(9, 0),
            recurrence=RECURRENCE_EVERY_N_DAYS,
            interval_days=2,
            skip_holidays=True,
            work_calendar=self.calendar,
        )

        occurrences = self.store.list_today(date(2026, 9, 21), self.calendar)

        self.assertEqual(
            [item.due_date for item in occurrences],
            [date(2026, 9, 18), date(2026, 9, 21)],
        )

    def test_shared_database_claims_due_reminder_once(self):
        today = date(2026, 7, 29)
        self.store.add_todo("喝水", "", today, time(9, 0), work_calendar=self.calendar)
        other_store = TodoStore(self.db_path)

        first = self.store.claim_due_reminders(
            datetime(2026, 7, 29, 9, 30),
            self.calendar,
        )
        second = other_store.claim_due_reminders(
            datetime(2026, 7, 29, 9, 30),
            self.calendar,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
