import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage import MemeStore, is_safe_category_segment, scan_pack_emojis


class PackStorageRuntimeTests(unittest.TestCase):
    def test_webui_scan_uses_runtime_image_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memes_dir = Path(temp_dir) / "memes"
            category_dir = memes_dir / "happy"
            category_dir.mkdir(parents=True)
            (category_dir / "z.webp").write_bytes(b"webp")
            (category_dir / "a.BMP").write_bytes(b"bmp")
            (category_dir / "index.json").write_text("{}", encoding="utf-8")

            scanned = scan_pack_emojis(memes_dir)
            self.assertEqual(set(scanned), {"开心"})
            self.assertEqual(len(scanned["开心"]), 2)
            self.assertTrue(all(name.startswith("meme_") for name in scanned["开心"]))

    def test_unicode_category_names_share_the_same_safe_storage_contract(self):
        self.assertTrue(is_safe_category_segment("猫猫表情"))
        self.assertFalse(is_safe_category_segment("../outside"))
        self.assertFalse(is_safe_category_segment("bad:name"))

        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "packs" / "cats")
            saved = store.save_image(b"unicode-category", ["其他"], ".png", None)
            self.assertTrue(saved.path.is_file())
            self.assertEqual(store.pick_image("其他"), saved.path)
            self.assertEqual(
                store.load_catalog()["items"][0]["filename"],
                saved.path.name,
            )

    def test_capture_store_isolated_inside_pack_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "packs" / "cats"
            store = MemeStore(pack_dir)

            first = store.save_image(b"not-a-real-image", ["开心"], ".png", None)
            duplicate = store.save_image(b"not-a-real-image", ["开心"], ".png", None)

            self.assertEqual(first.status, "saved")
            self.assertEqual(duplicate.status, "duplicate")
            self.assertTrue(first.path.is_relative_to(pack_dir))
            self.assertEqual(store.directory_categories(), set())
            self.assertTrue(store.memes_dir.joinpath("index.json").is_file())
            self.assertTrue(store.memes_dir.joinpath("README.md").is_file())
            catalog = store.load_catalog()
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
            catalog = store.load_catalog()
            self.assertEqual(catalog["items"][0]["description"], "保留描述")
            self.assertTrue(store.memes_dir.joinpath("README.md").is_file())

    def test_duplicate_repairs_readme_without_replacing_existing_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "packs" / "cats"
            store = MemeStore(pack_dir)
            saved = store.save_image(b"duplicate-content", ["开心"], ".png", None)
            saved.path.parent.joinpath("README.md").unlink()
            store.write_catalog(
                [{"filename": saved.path.name, "description": "详细描述", "tags": ["标签"]}],
            )
            saved.path.parent.joinpath("README.md").unlink()

            duplicate = store.save_image(b"duplicate-content", ["开心"], ".png", None)

            self.assertEqual(duplicate.status, "duplicate")
            self.assertEqual(
                store.load_catalog()["items"][0]["description"],
                "详细描述",
            )
            self.assertTrue(store.memes_dir.joinpath("README.md").is_file())

    def test_reconcile_removes_catalog_entries_for_deleted_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "packs" / "cats")
            saved = store.save_image(b"catalog-content", ["开心"], ".png", None)
            store.upsert_catalog_entry(
                {"filename": saved.path.name, "description": "保留"},
            )
            saved.path.unlink()

            self.assertEqual(store.reconcile_catalogs(), 1)
            self.assertEqual(store.load_catalog()["items"], [])

    @unittest.skip("legacy category renumbering is retired")
    def test_reindex_category_fills_gaps_and_preserves_index_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "packs" / "cats")
            category_dir = store.memes_dir / "happy"
            category_dir.mkdir(parents=True)
            (category_dir / "happy_0001.png").write_bytes(b"first")
            (category_dir / "happy_0003.gif").write_bytes(b"third")
            store.write_catalog(
                "happy",
                [
                    {
                        "id": "happy_0001",
                        "filename": "happy_0001.png",
                        "description": "第一张",
                        "indexed": True,
                        "send_count": 4,
                    },
                    {
                        "id": "happy_0003",
                        "filename": "happy_0003.gif",
                        "description": "第三张",
                        "emotion": "开心",
                        "tags": ["庆祝"],
                        "indexed": True,
                        "send_count": 2,
                    },
                ],
                {"classification_index_complete": True},
            )

            mapping = store.reindex_category("happy")

            self.assertEqual(
                mapping[category_dir / "happy_0003.gif"].name,
                "happy_0002.gif",
            )
            self.assertTrue((category_dir / "happy_0002.gif").is_file())
            catalog = store.load_catalog("happy")
            entries = {item["filename"]: item for item in catalog["items"]}
            self.assertEqual(entries["happy_0002.gif"]["id"], "happy_0002")
            self.assertEqual(entries["happy_0002.gif"]["description"], "第三张")
            self.assertEqual(entries["happy_0002.gif"]["emotion"], "开心")
            self.assertEqual(entries["happy_0002.gif"]["tags"], ["庆祝"])
            self.assertTrue(entries["happy_0002.gif"]["indexed"])
            self.assertEqual(entries["happy_0002.gif"]["send_count"], 2)
            self.assertTrue(catalog["classification_index_complete"])

    def test_load_catalog_accepts_bom_and_legacy_mapping_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            category_dir = Path(temp_dir) / "packs" / "cats" / "memes" / "happy"
            category_dir.mkdir(parents=True)
            category_dir.joinpath("index.json").write_text(
                '{"images": {"old.png": {"description": "旧描述"}}}',
                encoding="utf-8-sig",
            )

            catalog = MemeStore(category_dir.parent.parent).load_catalog("happy")

            self.assertEqual(catalog["items"][0]["filename"], "old.png")
            self.assertEqual(catalog["items"][0]["description"], "旧描述")

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

    def test_original_manager_migration_repairs_empty_index_after_marker(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "meme_manager"
            target_dir = Path(temp_dir) / "meme_manager_master"
            source_category = source_dir / "happy"
            target_category = (
                target_dir / "packs" / config.LEGACY_MIGRATED_PACK_ID / "memes" / "happy"
            )
            source_category.mkdir(parents=True)
            target_category.mkdir(parents=True)
            (source_category / "happy_0001.png").write_bytes(b"source-image")
            (target_category / "happy_0001.png").write_bytes(b"target-image")
            (source_category / "index.json").write_text(
                '{"items": [{"filename": "happy_0001.png", "description": "原始描述"}]}',
                encoding="utf-8",
            )
            (target_category / "index.json").write_text(
                '{"items": []}',
                encoding="utf-8",
            )
            marker_path = target_dir / "migration" / "original_meme_manager_imported.json"
            marker_path.parent.mkdir(parents=True)
            marker_path.write_text(
                '{"source": "' + str(source_dir).replace("\\", "\\\\") + '", '
                '"imported_pack_ids": ["legacy-migrated"]}',
                encoding="utf-8",
            )

            with patch.object(config, "_original_manager_data_dir", return_value=source_dir):
                config.migrate_original_manager_data_if_needed(target_dir)

            repaired = MemeStore(target_dir / "packs" / config.LEGACY_MIGRATED_PACK_ID)
            self.assertEqual(
                repaired.load_catalog("happy")["items"][0]["description"],
                "原始描述",
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
