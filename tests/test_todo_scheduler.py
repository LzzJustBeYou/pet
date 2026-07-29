import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QCoreApplication

from holiday_calendar import HolidayCalendar
from todo_scheduler import DEFAULT_POLL_INTERVAL_MS, TodoScheduler
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

    def test_default_poll_interval_is_one_minute(self):
        scheduler = TodoScheduler(self.store, self.calendar)

        self.assertEqual(DEFAULT_POLL_INTERVAL_MS, 60000)
        self.assertEqual(scheduler.interval_ms, 60000)

    def test_poll_interval_can_be_overridden(self):
        scheduler = TodoScheduler(self.store, self.calendar, interval_ms=30000)

        self.assertEqual(scheduler.interval_ms, 30000)


if __name__ == "__main__":
    unittest.main()
