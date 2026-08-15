import json
import tempfile
import unittest
from pathlib import Path

from storage import MemeStore


class TagLookupIndexTests(unittest.TestCase):
    def test_catalog_migrates_legacy_category_and_marks_ambiguous_items(self):
        normalized = MemeStore._normalize_catalog_items(
            [
                {"filename": "category.png", "category": "happy", "tags": ["工作"]},
                {"filename": "tag.png", "tags": ["尴尬"]},
                {"filename": "ambiguous.png", "tags": ["尴尬", "开心"]},
            ]
        )

        self.assertEqual(normalized[0]["primary_category"], "开心")
        self.assertEqual(normalized[1]["primary_category"], "尴尬")
        self.assertEqual(normalized[2]["primary_category"], "")
        self.assertEqual(
            normalized[2]["primary_category_status"],
            "needs_reindex",
        )

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

    def test_indexed_selection_can_be_restricted_to_model_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            first = store.save_image(b"first", ["开心"], ".png", None)
            second = store.save_image(b"second", ["开心"], ".png", None)
            items = []
            for item in store.load_catalog()["items"]:
                updated = dict(item)
                updated["indexed"] = True
                items.append(updated)
            store.write_catalog(items)

            selected = store.pick_indexed_image(
                "开心",
                candidate_filenames=[first.path.name],
                repeat_window=0,
            )

            self.assertEqual(selected, first.path)
            self.assertNotEqual(selected, second.path)

    def test_primary_lookup_ignores_secondary_semantic_tags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            result = store.save_image(b"awkward-image", ["开心"], ".png", None)
            item = dict(store.load_catalog()["items"][0])
            item.update(
                {
                    "indexed": True,
                    "primary_category": "尴尬",
                    "semantic_tags": ["开心"],
                }
            )
            store.write_catalog([item])

            self.assertIsNone(
                store.pick_indexed_primary_image("开心", repeat_window=0)
            )
            self.assertEqual(
                store.pick_indexed_primary_image("尴尬", repeat_window=0),
                result.path,
            )

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
