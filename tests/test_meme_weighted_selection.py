import tempfile
import unittest
from pathlib import Path

from storage import MemeStore


class MemeWeightedSelectionTests(unittest.TestCase):
    def test_unsent_image_has_full_weight(self):
        self.assertEqual(
            MemeStore._send_weight({}, now=1000, repeat_window=300),
            1.0,
        )

    def test_weight_keeps_decreasing_as_send_count_grows(self):
        weights = [
            MemeStore._send_weight(
                {"send_count": count, "last_sent_at": 1000},
                now=1000,
                repeat_window=300,
            )
            for count in (1, 2, 5, 10)
        ]

        self.assertGreater(weights[0], weights[1])
        self.assertGreater(weights[1], weights[2])
        self.assertGreater(weights[2], weights[3])

    def test_weight_recovers_to_count_penalty_after_repeat_window(self):
        weight = MemeStore._send_weight(
            {"send_count": 5, "last_sent_at": 1000},
            now=1300,
            repeat_window=300,
        )

        self.assertAlmostEqual(weight, 1 / (1 + 0.35 * 5))

    def test_weight_never_falls_below_minimum(self):
        weight = MemeStore._send_weight(
            {"send_count": 100000, "last_sent_at": 1000},
            now=1000,
            repeat_window=300,
        )

        self.assertEqual(weight, 0.1)

    def test_invalid_and_negative_statistics_use_safe_defaults(self):
        invalid = MemeStore._send_weight(
            {"send_count": "not-a-number", "last_sent_at": "invalid"},
            now=1000,
            repeat_window=300,
        )
        negative = MemeStore._send_weight(
            {"send_count": -5, "last_sent_at": 1000},
            now=1000,
            repeat_window=300,
        )

        self.assertEqual(invalid, 1.0)
        self.assertAlmostEqual(negative, 0.35)

    def test_non_positive_repeat_window_disables_time_decay(self):
        weight = MemeStore._send_weight(
            {"send_count": 5, "last_sent_at": 1000},
            now=1000,
            repeat_window=0,
        )

        self.assertEqual(weight, 1.0)

    def test_mark_image_sent_persists_count_and_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            saved = store.save_image(b"image", ["happy"], ".png", None)

            marked = store.mark_image_sent(saved.path, sent_at=1234)
            item = store.load_catalog()["items"][0]

            self.assertEqual(marked["send_count"], 1)
            self.assertEqual(marked["last_sent_at"], 1234.0)
            self.assertEqual(item["send_count"], 1)
            self.assertEqual(item["last_sent_at"], 1234.0)

            store.mark_image_sent(saved.path, sent_at=2345)
            item = store.load_catalog()["items"][0]
            self.assertEqual(item["send_count"], 2)
            self.assertEqual(item["last_sent_at"], 2345.0)

    def test_mark_image_sent_ignores_outside_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = MemeStore(root / "pack")
            saved = store.save_image(b"image", ["happy"], ".png", None)
            outside = root / "outside.png"
            outside.write_bytes(b"outside")

            self.assertIsNone(store.mark_image_sent(outside, sent_at=1234))
            item = store.load_catalog()["items"][0]
            self.assertEqual(item["send_count"], 0)
            self.assertEqual(item["last_sent_at"], 0)
            self.assertTrue(saved.path.is_file())


if __name__ == "__main__":
    unittest.main()
