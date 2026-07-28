import tempfile
import unittest
from pathlib import Path

from storage import MemeStore


class PackStorageRuntimeTests(unittest.TestCase):
    def test_capture_store_isolated_inside_pack_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "packs" / "cats"
            store = MemeStore(pack_dir)

            first = store.save_image(b"not-a-real-image", "happy", ".png", None)
            duplicate = store.save_image(b"not-a-real-image", "happy", ".png", None)

            self.assertEqual(first.status, "saved")
            self.assertEqual(duplicate.status, "duplicate")
            self.assertTrue(first.path.is_relative_to(pack_dir))
            self.assertEqual(store.directory_categories(), {"happy"})

    def test_catalog_round_trip_preserves_category_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "packs" / "cats")
            store.write_catalog(
                "happy",
                [{"filename": "happy_0001.png", "description": "庆祝"}],
                {"provider_id": "test-provider"},
            )

            catalog = store.load_catalog("happy")
            self.assertEqual(catalog["category"], "happy")
            self.assertEqual(catalog["provider_id"], "test-provider")
            self.assertEqual(catalog["items"][0]["filename"], "happy_0001.png")


if __name__ == "__main__":
    unittest.main()
