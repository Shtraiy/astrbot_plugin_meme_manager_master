import json
import tempfile
import unittest
from pathlib import Path

from storage import MemeStore


class TagLookupIndexTests(unittest.TestCase):
    def test_lookup_index_deduplicates_one_image_across_multiple_tags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            result = store.save_image(
                b"lookup-image",
                ["开心", "悲伤"],
                ".png",
                None,
            )
            item = dict(store.load_catalog()["items"][0])
            item["indexed"] = True
            store.write_catalog([item])

            lookup = json.loads(
                (store.memes_dir / "tag_index.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                lookup["by_tag"]["开心"],
                [item["id"]],
            )
            self.assertEqual(
                lookup["by_tag"]["悲伤"],
                [item["id"]],
            )
            self.assertEqual(list(lookup["items"]), [item["id"]])
            self.assertEqual(
                lookup["items"][item["id"]]["filename"],
                result.path.name,
            )

    def test_missing_lookup_index_is_rebuilt_for_bot_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            result = store.save_image(b"selectable-image", ["开心"], ".png", None)
            item = dict(store.load_catalog()["items"][0])
            item["indexed"] = True
            store.write_catalog([item])
            (store.memes_dir / "tag_index.json").unlink()

            selected = store.pick_indexed_image("happy", repeat_window=0)

            self.assertEqual(selected, result.path)
            self.assertTrue((store.memes_dir / "tag_index.json").is_file())

    def test_unindexed_item_is_not_in_bot_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            result = store.save_image(b"pending-image", ["开心"], ".png", None)
            lookup = json.loads(
                (store.memes_dir / "tag_index.json").read_text(encoding="utf-8")
            )

            self.assertNotIn(result.path.stem, lookup["items"])
            self.assertEqual(lookup["by_tag"], {})


if __name__ == "__main__":
    unittest.main()
