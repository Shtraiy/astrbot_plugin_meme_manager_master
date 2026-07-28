import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            self.assertTrue(first.path.parent.joinpath("index.json").is_file())
            self.assertTrue(first.path.parent.joinpath("README.md").is_file())
            catalog = store.load_catalog("happy")
            self.assertEqual(
                [item["filename"] for item in catalog["items"]],
                [first.path.name],
            )

    def test_reconcile_repairs_copied_category_without_overwriting_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "packs" / "cats"
            category_dir = pack_dir / "memes" / "happy"
            category_dir.mkdir(parents=True)
            image_path = category_dir / "old.png"
            image_path.write_bytes(b"copied-image")
            category_dir.joinpath("index.json").write_text(
                '{"version": 1, "category": "happy", "items": '
                '[{"filename": "old.png", "description": "保留描述", '
                '"tags": ["开心"]}]}',
                encoding="utf-8",
            )

            store = MemeStore(pack_dir)
            self.assertEqual(store.reconcile_catalogs(), 1)
            self.assertEqual(store.reconcile_catalogs(), 0)
            catalog = store.load_catalog("happy")
            self.assertEqual(catalog["items"][0]["description"], "保留描述")
            self.assertTrue(category_dir.joinpath("README.md").is_file())

    def test_duplicate_repairs_readme_without_replacing_existing_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "packs" / "cats"
            store = MemeStore(pack_dir)
            saved = store.save_image(b"duplicate-content", "happy", ".png", None)
            saved.path.parent.joinpath("README.md").unlink()
            store.write_catalog(
                "happy",
                [{"filename": saved.path.name, "description": "详细描述", "tags": ["标签"]}],
            )
            saved.path.parent.joinpath("README.md").unlink()

            duplicate = store.save_image(b"duplicate-content", "happy", ".png", None)

            self.assertEqual(duplicate.status, "duplicate")
            self.assertEqual(
                store.load_catalog("happy")["items"][0]["description"],
                "详细描述",
            )
            self.assertTrue(saved.path.parent.joinpath("README.md").is_file())

    def test_original_manager_direct_categories_are_migrated_with_indexes(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "meme_manager"
            target_dir = Path(temp_dir) / "meme_manager_master"
            category_dir = source_dir / "happy"
            category_dir.mkdir(parents=True)
            (category_dir / "happy_0001.png").write_bytes(b"copied-image")
            (category_dir / "index.json").write_text(
                '{"version": 1, "category": "happy", "items": '
                '[{"filename": "happy_0001.png", "description": "原版描述"}]}',
                encoding="utf-8",
            )
            (category_dir / "README.md").write_text(
                "# happy 表情包索引\n", encoding="utf-8"
            )

            with patch.object(config, "_original_manager_data_dir", return_value=source_dir):
                config.migrate_original_manager_data_if_needed(target_dir)

            migrated = target_dir / "packs" / "legacy-migrated" / "memes" / "happy"
            self.assertTrue((migrated / "index.json").is_file())
            self.assertTrue((migrated / "README.md").is_file())
            self.assertEqual(
                MemeStore(target_dir / "packs" / "legacy-migrated")
                .load_catalog("happy")["items"][0]["description"],
                "原版描述",
            )

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
