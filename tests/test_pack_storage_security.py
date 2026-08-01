import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.fakes import install_package_alias


install_package_alias()

from meme_manager_master.backend import pack_storage  # noqa: E402


class PackStorageSecurityTests(unittest.TestCase):
    def _make_outside_pack(self, root: Path) -> tuple[Path, Path]:
        packs_dir = root / "packs"
        outside_dir = root / "outside"
        packs_dir.mkdir()
        (outside_dir / "memes" / "happy").mkdir(parents=True)
        (outside_dir / "manifest.json").write_text(
            '{"id":"outside","name":"Outside","version":"1",'
            '"categories":{"happy":{}}}',
            encoding="utf-8",
        )
        return packs_dir, outside_dir

    def test_pack_detail_rejects_directory_traversal_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir, _outside_dir = self._make_outside_pack(Path(temp_dir))
            with patch.object(pack_storage, "PACKS_DIR", packs_dir):
                with self.assertRaises(ValueError):
                    pack_storage.get_pack_detail("../outside")

    def test_set_default_rejects_directory_traversal_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir, _outside_dir = self._make_outside_pack(Path(temp_dir))
            with (
                patch.object(pack_storage, "PACKS_DIR", packs_dir),
                patch.object(pack_storage, "_load_selection_rules", return_value={"rules": []}),
                patch.object(pack_storage, "_save_selection_rules"),
            ):
                with self.assertRaises(ValueError):
                    pack_storage.set_default_pack("../outside")

    def test_uninstall_rejects_directory_traversal_without_deleting_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir, outside_dir = self._make_outside_pack(Path(temp_dir))
            with (
                patch.object(pack_storage, "PACKS_DIR", packs_dir),
                patch.object(pack_storage, "PLUGIN_DATA_DIR", Path(temp_dir) / "data"),
                patch.object(pack_storage, "_current_default_pack_id", return_value=""),
                patch.object(pack_storage, "_load_registry", return_value={"installed_packs": []}),
                patch.object(pack_storage, "_save_registry"),
            ):
                with self.assertRaises(ValueError):
                    pack_storage.uninstall_pack("../outside")
            self.assertTrue(outside_dir.exists())

    def test_backup_output_directory_stays_under_backup_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backup_root = root / "backup"
            allowed = backup_root / "exports"
            outside = root / "outside"
            with patch.object(pack_storage, "BACKUP_DIR", backup_root):
                self.assertEqual(
                    pack_storage._resolve_backup_output_dir(str(allowed)),
                    allowed.resolve(),
                )
                with self.assertRaises(ValueError):
                    pack_storage._resolve_backup_output_dir(str(outside))

    def test_github_archive_rejects_oversized_stream_without_writing(self):
        class Response:
            status_code = 200
            headers = {}
            content = b"legacy content"

            def iter_content(self, chunk_size):
                yield b"12345"
                yield b"67890"

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "remote.zip"
            with (
                patch.object(pack_storage, "MAX_REMOTE_ARCHIVE_BYTES", 8),
                patch.object(
                    pack_storage,
                    "_http_get_with_optional_acceleration",
                    return_value=Response(),
                ),
            ):
                with self.assertRaises(ValueError):
                    pack_storage._download_github_archive(
                        "owner/repo", "main", target
                    )
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
