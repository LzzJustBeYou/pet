import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from health_reminder import HealthReminderController


class HealthReminderControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = HealthReminderController(long_break_every=2)

    def tearDown(self):
        self.controller.stop_all()

    def test_completing_long_break_starts_a_new_break_cycle(self):
        self.controller._completed_breaks = 1

        self.controller.start_break_now()
        self.assertEqual(self.controller._break_kind, "long")
        self.controller._finish_break()

        self.assertEqual(self.controller._completed_breaks, 0)
        self.controller.start_break_now()
        self.assertEqual(self.controller._break_kind, "micro")


if __name__ == "__main__":
    unittest.main()
