import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QRect, QSize, Qt
from PyQt5.QtGui import QImage, QImageReader
from PyQt5.QtWidgets import QApplication

from animation import (
    ANIMATION_SPECS,
    GifVisual,
    SpriteAtlasPlayer,
    load_gif_visual,
    scaled_canvas_size,
)
from pet_package import load_pet_package


ROOT = Path(__file__).resolve().parents[1]


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_standard_frame_counts_and_jumping_duration(self):
        self.assertEqual(len(ANIMATION_SPECS["idle"].durations_ms), 6)
        self.assertEqual(len(ANIMATION_SPECS["running-right"].durations_ms), 8)
        self.assertEqual(len(ANIMATION_SPECS["waving"].durations_ms), 4)
        self.assertEqual(len(ANIMATION_SPECS["jumping"].durations_ms), 5)
        self.assertEqual(sum(ANIMATION_SPECS["jumping"].durations_ms), 840)

    def test_atlas_player_scales_proportionally_and_builds_masks(self):
        package = load_pet_package(ROOT / "pets" / "xiaoba")
        player = SpriteAtlasPlayer()
        frames = []
        player.frame_changed.connect(frames.append)
        player.load(package, 100)

        self.assertEqual((player.display_size.width(), player.display_size.height()), (92, 100))
        window_region, interaction_region = player.mask_regions()
        self.assertFalse(window_region.isEmpty())
        self.assertFalse(interaction_region.isEmpty())

        player.play("idle", True)
        player._timer.stop()
        self.assertEqual((frames[-1].width(), frames[-1].height()), (92, 100))

    def test_gif_visual_reads_all_frames_without_manual_jump(self):
        gif_path = ROOT / "actions" / "chikawa" / "臭臭小八.gif"
        reader = QImageReader(str(gif_path))
        first_frame = reader.read()
        self.assertFalse(first_frame.isNull())

        frame_count = 1
        while True:
            frame = reader.read()
            if frame.isNull():
                break
            frame_count += 1

        self.assertGreater(frame_count, 1)

        def alpha_bbox(image):
            min_x, min_y = image.width(), image.height()
            max_x, max_y = -1, -1
            for y in range(image.height()):
                for x in range(image.width()):
                    if image.pixelColor(x, y).alpha() > 0:
                        min_x = min(min_x, x)
                        min_y = min(min_y, y)
                        max_x = max(max_x, x)
                        max_y = max(max_y, y)
            return None if max_x < 0 else (min_x, min_y, max_x + 1, max_y + 1)

        visual = load_gif_visual(str(gif_path))
        first_bbox = alpha_bbox(first_frame)
        union_bbox = alpha_bbox(visual.union_image)

        self.assertIsNotNone(first_bbox)
        self.assertIsNotNone(union_bbox)
        self.assertLessEqual(union_bbox[0], first_bbox[0])
        self.assertLess(union_bbox[1], first_bbox[1])
        self.assertGreater(union_bbox[2], first_bbox[2])
        self.assertGreater(union_bbox[3], first_bbox[3])

    def test_opaque_gif_visual_uses_the_full_canvas_as_its_mask(self):
        image = QImage(20, 10, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.white)

        region = GifVisual(QSize(20, 10), image).mask_region(100)

        self.assertFalse(region.isEmpty())
        self.assertEqual(region.boundingRect(), QRect(0, 0, 200, 100))

    def test_one_shot_emits_finished_after_final_frame(self):
        package = load_pet_package(ROOT / "pets" / "xiaoba")
        player = SpriteAtlasPlayer()
        finished = []
        player.animation_finished.connect(finished.append)
        player.load(package, 100)
        player.play("waving", False)
        player._timer.stop()

        for _ in range(4):
            player._advance_frame()
            player._timer.stop()

        self.assertEqual(finished, ["waving"])


if __name__ == "__main__":
    unittest.main()
