import unittest

from PyQt5.QtCore import QCoreApplication, QPoint

from interaction import PetInteractionController


class InteractionControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.controller = PetInteractionController(hover_delay_ms=0)
        self.requests = []
        self.controller.animation_requested.connect(
            lambda state, loop: self.requests.append((state, loop))
        )
        self.controller.activate(True)

    def test_hover_triggers_once_per_entry(self):
        self.controller.pointer_enter()
        self.app.processEvents()
        self.app.processEvents()

        self.assertEqual(self.requests[-1], ("jumping", False))
        request_count = len(self.requests)
        self.controller.pointer_enter()
        self.app.processEvents()
        self.assertEqual(len(self.requests), request_count)

        self.controller.animation_finished("jumping")
        self.controller.pointer_leave()
        self.controller.pointer_enter()
        self.app.processEvents()
        self.assertEqual(self.requests[-1], ("jumping", False))

    def test_six_pixels_without_drag_does_not_trigger_click_animation(self):
        self.controller.press(QPoint(0, 0))
        update = self.controller.move(QPoint(6, 0))

        self.assertFalse(update.dragging)
        self.assertEqual(self.controller.release(), "click")
        self.assertEqual(self.requests[-1], ("idle", True))

    def test_hover_animation_returns_to_idle_when_finished(self):
        self.controller.pointer_enter()
        self.app.processEvents()
        self.app.processEvents()

        self.controller.animation_finished("jumping")
        self.assertEqual(self.requests[-1], ("idle", True))

    def test_horizontal_drag_selects_direction_and_returns_to_idle(self):
        self.controller.press(QPoint(10, 10))
        update = self.controller.move(QPoint(17, 10))

        self.assertTrue(update.dragging)
        self.assertEqual(update.direction, "right")
        self.assertEqual(self.requests[-1], ("running-right", True))
        self.assertEqual(self.controller.release(), "drag")
        self.assertEqual(self.requests[-1], ("idle", True))

    def test_vertical_drag_stays_idle_until_horizontal_direction_exists(self):
        self.controller.press(QPoint(10, 10))
        update = self.controller.move(QPoint(10, 17))

        self.assertTrue(update.dragging)
        self.assertIsNone(update.direction)
        self.assertEqual(self.requests[-1], ("idle", True))

        update = self.controller.move(QPoint(13, 20))
        self.assertEqual(update.direction, "right")
        self.assertEqual(self.requests[-1], ("running-right", True))

    def test_drag_interrupts_hover_animation(self):
        self.controller.pointer_enter()
        self.app.processEvents()
        self.app.processEvents()
        self.assertEqual(self.requests[-1], ("jumping", False))

        self.controller.press(QPoint(0, 0))
        self.controller.move(QPoint(-7, 0))

        self.assertEqual(self.requests[-1], ("running-left", True))


if __name__ == "__main__":
    unittest.main()
