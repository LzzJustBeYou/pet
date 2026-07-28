import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from animation import ANIMATION_SPECS, SpriteAtlasPlayer, scaled_canvas_size
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
