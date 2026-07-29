import tempfile
import unittest
from pathlib import Path

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtTest import QTest

from todo_notifier import (
    CALENDAR_CHANGE_KIND,
    TODO_CHANGE_KIND,
    TodoChangeNotifier,
    signal_path_for_database,
)


class TodoChangeNotifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.signal_path = Path(self.temp_dir.name) / "todo_changed.signal"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_signal_path_lives_next_to_database(self):
        db_path = Path(self.temp_dir.name) / "todo.sqlite3"

        self.assertEqual(
            signal_path_for_database(db_path),
            Path(self.temp_dir.name) / "todo_changed.signal",
        )

    def test_change_is_observed_by_another_notifier(self):
        sender = TodoChangeNotifier(self.signal_path, debounce_ms=10)
        receiver = TodoChangeNotifier(self.signal_path, debounce_ms=10)
        events = []
        receiver.changed.connect(events.append)
        self.app.processEvents()

        sender.notify_change(TODO_CHANGE_KIND)
        self._wait_for_events(events)

        self.assertIn(TODO_CHANGE_KIND, events)
        sender.stop()
        receiver.stop()
        sender.deleteLater()
        receiver.deleteLater()

    def test_calendar_change_kind_is_preserved(self):
        sender = TodoChangeNotifier(self.signal_path, debounce_ms=10)
        receiver = TodoChangeNotifier(self.signal_path, debounce_ms=10)
        events = []
        receiver.changed.connect(events.append)
        self.app.processEvents()

        sender.notify_change(CALENDAR_CHANGE_KIND)
        self._wait_for_events(events)

        self.assertIn(CALENDAR_CHANGE_KIND, events)
        sender.stop()
        receiver.stop()
        sender.deleteLater()
        receiver.deleteLater()

    def _wait_for_events(self, events):
        for _ in range(50):
            self.app.processEvents()
            if events:
                return
            QTest.qWait(20)
        self.fail("notifier did not emit a change event")


if __name__ == "__main__":
    unittest.main()
