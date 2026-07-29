import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QCoreApplication

from holiday_calendar import HolidayCalendar
from todo_scheduler import (
    DEFAULT_POLL_INTERVAL_MS,
    DEFAULT_POLL_STEP_MINUTES,
    TodoScheduler,
    milliseconds_until_next_step,
)
from todo_store import TodoStore


ROOT = Path(__file__).resolve().parents[1]


class TodoSchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = TodoStore(Path(self.temp_dir.name) / "todo.sqlite3")
        self.calendar = HolidayCalendar(
            user_path=Path(self.temp_dir.name) / "calendar.json",
            bundle_path=ROOT / "calendar_data" / "cn_workdays.json",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_poll_step_is_five_minutes(self):
        scheduler = TodoScheduler(self.store, self.calendar)

        self.assertEqual(DEFAULT_POLL_STEP_MINUTES, 5)
        self.assertEqual(DEFAULT_POLL_INTERVAL_MS, 300000)
        self.assertEqual(scheduler.poll_step_minutes, 5)
        self.assertEqual(scheduler.interval_ms, 300000)

    def test_poll_step_can_be_overridden(self):
        scheduler = TodoScheduler(self.store, self.calendar, poll_step_minutes=10)

        self.assertEqual(scheduler.poll_step_minutes, 10)
        self.assertEqual(scheduler.interval_ms, 600000)

    def test_next_step_delay_aligns_to_clock_boundary(self):
        self.assertEqual(
            milliseconds_until_next_step(datetime(2026, 1, 1, 14, 3, 30)),
            90000,
        )
        self.assertEqual(
            milliseconds_until_next_step(datetime(2026, 1, 1, 14, 5, 0)),
            300000,
        )
        self.assertEqual(
            milliseconds_until_next_step(datetime(2026, 1, 1, 23, 58, 0)),
            120000,
        )


if __name__ == "__main__":
    unittest.main()
