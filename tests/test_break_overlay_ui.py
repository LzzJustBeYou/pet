import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from break_overlay import BreakOverlay


SCREEN = QRect(0, 0, 1920, 1080)


class BreakOverlayUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_show_micro_break_sets_ui(self):
        overlay = BreakOverlay()
        overlay.show_break("micro", 20, SCREEN)
        self.assertTrue(overlay.isVisible())
        self.assertEqual(overlay.title_label.text(), "休息一下")
        self.assertEqual(overlay.countdown_label.text(), "20")
        self.assertEqual(overlay.progress.maximum(), 20)
        self.assertEqual(overlay.progress.value(), 20)
        overlay.close()

    def test_show_long_break_sets_ui(self):
        overlay = BreakOverlay()
        overlay.show_break("long", 300, SCREEN)
        self.assertEqual(overlay.title_label.text(), "长休息，站起来走走")
        self.assertEqual(overlay.countdown_label.text(), "300")
        overlay.close()

    def test_update_remaining_updates_labels_and_progress(self):
        overlay = BreakOverlay()
        overlay.show_break("micro", 20, SCREEN)
        overlay.update_remaining(7)
        self.assertEqual(overlay.countdown_label.text(), "7")
        self.assertEqual(overlay.progress.value(), 7)
        overlay.close()

    def test_skip_button_emits_and_hides(self):
        overlay = BreakOverlay()
        skipped = []
        overlay.skipped.connect(lambda: skipped.append(True))
        overlay.show_break("micro", 20, SCREEN)
        QApplication.processEvents()
        QTest.mouseClick(overlay.skip_button, Qt.LeftButton)
        self.assertEqual(skipped, [True])
        self.assertFalse(overlay.isVisible())
        overlay.close()

    def test_escape_key_skips(self):
        overlay = BreakOverlay()
        skipped = []
        overlay.skipped.connect(lambda: skipped.append(True))
        overlay.show_break("micro", 20, SCREEN)
        QApplication.processEvents()
        QTest.keyClick(overlay, Qt.Key_Escape)
        self.assertEqual(skipped, [True])
        self.assertFalse(overlay.isVisible())
        overlay.close()

    def test_position_centered_on_screen(self):
        overlay = BreakOverlay()
        overlay.show_break("micro", 20, SCREEN)
        center = overlay.frameGeometry().center()
        self.assertTrue(SCREEN.contains(center))
        overlay.close()

    def test_fullscreen_break_fills_screen(self):
        overlay = BreakOverlay()
        overlay.show_break("micro", 20, SCREEN, fullscreen=True)
        self.assertTrue(overlay.isVisible())
        self.assertEqual(overlay.frameGeometry(), SCREEN)
        self.assertEqual(overlay.size().width(), SCREEN.width())
        self.assertEqual(overlay.size().height(), SCREEN.height())
        self.assertIn("border-radius: 0", overlay._frame.styleSheet())
        overlay.close()

    def test_fullscreen_break_shows_mmss_countdown(self):
        overlay = BreakOverlay()
        overlay.show_break("micro", 20, SCREEN, fullscreen=True)
        self.assertEqual(overlay.countdown_label.text(), "0:20")
        overlay.update_remaining(305)
        self.assertEqual(overlay.countdown_label.text(), "5:05")
        overlay.close()

    def test_fullscreen_break_has_centered_skip_button(self):
        overlay = BreakOverlay()
        skipped = []
        overlay.skipped.connect(lambda: skipped.append(True))
        overlay.show_break("micro", 20, SCREEN, fullscreen=True)
        self.assertIsNotNone(overlay.skip_button)
        self.assertTrue(overlay.skip_button.isVisible())
        button_center_x = overlay.skip_button.geometry().center().x()
        overlay_center_x = overlay.width() // 2
        self.assertLess(abs(button_center_x - overlay_center_x), 4)
        QApplication.processEvents()
        QTest.mouseClick(overlay.skip_button, Qt.LeftButton)
        self.assertEqual(skipped, [True])
        self.assertFalse(overlay.isVisible())
        overlay.close()

    def test_fullscreen_break_escape_skips(self):
        overlay = BreakOverlay()
        skipped = []
        overlay.skipped.connect(lambda: skipped.append(True))
        overlay.show_break("micro", 20, SCREEN, fullscreen=True)
        QApplication.processEvents()
        QTest.keyClick(overlay, Qt.Key_Escape)
        QApplication.processEvents()
        self.assertEqual(skipped, [True])
        self.assertFalse(overlay.isVisible())
        overlay.close()

    def test_normal_break_restores_compact_size_after_fullscreen(self):
        overlay = BreakOverlay()
        overlay.show_break("micro", 20, SCREEN, fullscreen=True)
        overlay.show_break("micro", 20, SCREEN)
        self.assertEqual((overlay.width(), overlay.height()), (300, 240))
        self.assertIsNotNone(overlay.skip_button)
        self.assertEqual(overlay.countdown_label.text(), "20")
        self.assertIn("border-radius: 14px", overlay._frame.styleSheet())
        overlay.close()
