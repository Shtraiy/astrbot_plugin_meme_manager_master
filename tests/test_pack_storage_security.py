import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tests.fakes import install_package_alias
from storage import resolve_safe_category_dir


install_package_alias()

from meme_manager_master.backend import pack_storage  # noqa: E402


class PackStorageSecurityTests(unittest.TestCase):
    def test_remote_requests_disable_redirects(self):
        calls = []

        class Response:
            status_code = 200

        def fake_get(*args, **kwargs):
            calls.append((args, kwargs))
            return Response()

        with patch.object(
            pack_storage.requests, "get", side_effect=fake_get, create=True
        ):
            pack_storage._http_get_with_optional_acceleration(
                "https://github.com/example/project/archive/main.zip", timeout=5
            )

        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0][1]["allow_redirects"])

    def test_remote_requests_reject_non_https_targets(self):
        with patch.object(pack_storage.requests, "get", create=True) as request_get:
            with self.assertRaises(ValueError):
                pack_storage._http_get_with_optional_acceleration(
                    "http://example.com/archive.zip", timeout=5
                )
        request_get.assert_not_called()

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

    def test_selection_rules_reject_absolute_pack_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir, outside_dir = self._make_outside_pack(Path(temp_dir))
            rules = [
                {"id": "default-rule", "scope": "default", "pack_id": str(outside_dir)}
            ]
            with patch.object(pack_storage, "PACKS_DIR", packs_dir):
                with self.assertRaises(ValueError):
                    pack_storage._validate_and_normalize_rules(rules)

    def test_selection_rules_reject_parent_pack_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir, _outside_dir = self._make_outside_pack(Path(temp_dir))
            rules = [{"id": "default-rule", "scope": "default", "pack_id": "../outside"}]
            with patch.object(pack_storage, "PACKS_DIR", packs_dir):
                with self.assertRaises(ValueError):
                    pack_storage._validate_and_normalize_rules(rules)

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

    def test_upload_category_directory_stays_under_memes_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memes_root = Path(temp_dir) / "memes"
            outside = Path(temp_dir) / "outside"
            self.assertEqual(
                resolve_safe_category_dir(memes_root, "happy"),
                (memes_root / "happy").resolve(),
            )
            with self.assertRaises(ValueError):
                resolve_safe_category_dir(memes_root, "../outside")
            self.assertFalse(outside.exists())

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

    def test_extract_rejects_oversized_registry_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "oversized.zip"
            target_dir = root / "target"
            oversized = b"{" + b"x" * pack_storage.ARCHIVE_JSON_SIZE_LIMITS["registry.json"] + b"}"
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("registry.json", oversized)

            with self.assertRaises(ValueError):
                pack_storage._extract_zip_safely(archive_path, target_dir)
            self.assertFalse((target_dir / "registry.json").exists())


if __name__ == "__main__":
    unittest.main()
