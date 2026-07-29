import os
import tempfile
import unittest
from datetime import datetime, timedelta, time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from holiday_calendar import HolidayCalendar
from todo_models import RECURRENCE_NONE
from todo_models import local_now
from todo_store import TodoStore
from todo_ui import (
    TodoManagerWindow,
    TodoQuickPanel,
    calendar_errors_are_not_found,
    snap_time_to_step,
)


ROOT = Path(__file__).resolve().parents[1]


class TodoManagerWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = TodoStore(Path(self.temp_dir.name) / "todo.sqlite3")
        self.calendar = HolidayCalendar(
            user_path=Path(self.temp_dir.name) / "calendar.json",
            bundle_path=ROOT / "calendar_data" / "cn_workdays.json",
        )
        today = local_now().date()
        tomorrow = today + timedelta(days=1)
        self.store.add_todo(
            "今天的事",
            "",
            today,
            None,
            recurrence=RECURRENCE_NONE,
            work_calendar=self.calendar,
        )
        self.store.add_todo(
            "之后的事",
            "",
            tomorrow,
            time(10, 0),
            recurrence=RECURRENCE_NONE,
            work_calendar=self.calendar,
        )
        planned = self.store.list_planned(today, self.calendar)[0]
        self.store.complete_occurrence(planned.id)

        self.window = TodoManagerWindow(self.store, self.calendar)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def test_tabs_remain_clickable_after_selecting_todo(self):
        self.window.today_list.setCurrentRow(0)
        self.app.processEvents()
        self.assertIsNotNone(self.window._selected_occurrence_id)

        self.assertEqual(self.window.tabs.tabText(1), "便签")
        tab_bar = self.window.tabs.tabBar()
        QTest.mouseClick(
            tab_bar,
            Qt.LeftButton,
            pos=tab_bar.tabRect(1).center(),
        )
        self.app.processEvents()

        self.assertEqual(self.window.tabs.currentIndex(), 1)
        self.assertIsNone(self.window._selected_occurrence_id)

        QTest.mouseClick(
            tab_bar,
            Qt.LeftButton,
            pos=tab_bar.tabRect(2).center(),
        )
        self.app.processEvents()

        self.assertEqual(self.window.tabs.currentIndex(), 2)
        self.assertIsNone(self.window._selected_occurrence_id)

    def test_undated_toggle_saves_note_without_due_controls(self):
        self.window.start_new()
        self.window.title_edit.setText("没有日期的想法")
        self.window.has_time_check.setChecked(True)
        self.window.no_date_check.setChecked(True)
        self.app.processEvents()

        self.assertFalse(self.window.date_edit.isEnabled())
        self.assertFalse(self.window.has_time_check.isChecked())
        self.assertFalse(self.window.has_time_check.isEnabled())
        self.assertFalse(self.window.recurrence_combo.isEnabled())
        self.assertFalse(self.window.skip_holidays_check.isEnabled())

        self.window._save()
        self.app.processEvents()

        notes = self.store.list_undated()
        self.assertEqual([item.title for item in notes], ["没有日期的想法"])
        self.assertIsNone(notes[0].due_date)
        self.assertEqual(self.window.undated_list.count(), 1)
        self.assertIn("无日期", self.window.undated_list.item(0).text())

    def test_time_values_snap_to_five_minute_steps(self):
        self.assertEqual(snap_time_to_step(time(14, 0)), time(14, 0))
        self.assertEqual(snap_time_to_step(time(14, 1)), time(14, 5))
        self.assertEqual(snap_time_to_step(time(14, 5)), time(14, 5))
        self.assertEqual(snap_time_to_step(time(23, 59)), time(23, 55))

    def test_calendar_update_not_found_errors_are_classified(self):
        self.assertTrue(
            calendar_errors_are_not_found(
                [
                    "https://example.test/calendar.json: server replied: Not Found",
                    "https://cdn.example.test/calendar.json: server replied: not found",
                ]
            )
        )
        self.assertFalse(calendar_errors_are_not_found(["Connection refused"]))

    def test_quick_panel_shows_summary_and_opens_selected_todo(self):
        panel = TodoQuickPanel(self.store, self.calendar, visible_ms=1000)
        opened = []
        panel.manage_requested.connect(opened.append)
        panel.refresh()

        self.assertEqual(panel.count_label.text(), "1")
        item_button = panel.items_layout.itemAt(0).widget()

        QTest.mouseClick(item_button, Qt.LeftButton)
        self.app.processEvents()

        self.assertEqual(len(opened), 1)
        self.assertIsInstance(opened[0], int)
        panel.deleteLater()

    def test_quick_panel_only_lists_due_reminders(self):
        today = local_now().date()
        self.store.add_todo("只是便签", "", None, None)
        self.store.add_todo(
            "明天再说",
            "",
            today + timedelta(days=1),
            time(23, 55),
            recurrence=RECURRENCE_NONE,
            work_calendar=self.calendar,
        )
        panel = TodoQuickPanel(self.store, self.calendar, visible_ms=1000)
        panel.refresh()

        labels = [
            panel.items_layout.itemAt(index).widget().text()
            for index in range(panel.items_layout.count())
        ]
        self.assertTrue(any("今天的事" in label for label in labels))
        self.assertFalse(any("只是便签" in label for label in labels))
        self.assertFalse(any("明天再说" in label for label in labels))
        panel.deleteLater()

    def test_due_timed_todo_is_visible_in_manager_list(self):
        today = local_now().date()
        self.store.add_todo(
            "到点开会",
            "",
            today,
            time(10, 0),
            recurrence=RECURRENCE_NONE,
            work_calendar=self.calendar,
        )
        timed = next(
            item
            for item in self.store.list_today(today, self.calendar)
            if item.title == "到点开会"
        )
        due_now = datetime.combine(today, time(10, 0))

        self.window._fill_list(self.window.today_list, [timed], due_now)
        item = self.window.today_list.item(0)

        self.assertIn("🔔 已到 10:00", item.text())
        self.assertTrue(item.font().bold())

    def test_calendar_menu_does_not_offer_restore_bundled_calendar(self):
        self.window._rebuild_calendar_menu()

        labels = [action.text() for action in self.window.calendar_menu.actions()]

        self.assertIn("在线检查更新", labels)
        self.assertNotIn("恢复内置日历", labels)

    def test_refresh_clears_selection_when_external_delete_removes_todo(self):
        self.window.today_list.setCurrentRow(0)
        self.app.processEvents()
        occurrence_id = self.window._selected_occurrence_id
        self.assertIsNotNone(occurrence_id)

        self.store.delete_occurrence_only(occurrence_id)
        self.window.refresh()

        self.assertIsNone(self.window._selected_occurrence_id)
        self.assertEqual(self.window.title_edit.text(), "")


if __name__ == "__main__":
    unittest.main()
