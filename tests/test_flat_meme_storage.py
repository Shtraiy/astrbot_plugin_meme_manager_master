import json
import tempfile
import unittest
from pathlib import Path

from storage import MemeStore


class FlatMemeStorageTests(unittest.TestCase):
    def test_save_image_writes_meme_id_to_flat_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")

            result = store.save_image(
                b"flat-image", ["愤怒", "震惊"], ".png", None
            )

            self.assertEqual(result.path.parent, store.memes_dir)
            self.assertTrue(result.path.name.startswith("meme_"))
            self.assertEqual(
                store.load_catalog()["items"][0]["tags"], ["愤怒", "震惊"]
            )

    def test_reindex_flattens_legacy_category_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            legacy = store.memes_dir / "happy"
            legacy.mkdir(parents=True)
            (legacy / "happy_0001.png").write_bytes(b"legacy-image")
            (legacy / "index.json").write_text(
                json.dumps(
                    {
                        "category": "happy",
                        "items": [
                            {
                                "filename": "happy_0001.png",
                                "tags": ["生气"],
                                "description": "保留描述",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            first = store.reindex_flat_catalog()
            second = store.reindex_flat_catalog()

            self.assertEqual(first["migrated_file_count"], 1)
            self.assertEqual(second["migrated_file_count"], 0)
            self.assertEqual(len(list(store.memes_dir.glob("meme_*.png"))), 1)
            self.assertEqual(
                store.load_catalog()["items"][0]["tags"], ["开心", "愤怒"]
            )
            self.assertEqual(
                store.load_catalog()["items"][0]["description"], "保留描述"
            )
            self.assertFalse(legacy.exists())


if __name__ == "__main__":
    unittest.main()
