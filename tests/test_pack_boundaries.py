import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.community_pack_source import CommunityPackSource
from backend.pack_paths import PackPaths
from backend.pack_runtime import PackRuntime
from backend.pack_transfer import PackTransfer
from tests.fakes import install_package_alias


install_package_alias()

from meme_manager_master.backend import pack_storage  # noqa: E402


class PackBoundaryTests(unittest.TestCase):
    def test_pack_paths_keep_pack_and_backup_targets_bounded(self):
        paths = PackPaths(Path("/tmp/packs"), Path("/tmp/backups"))
        self.assertEqual(paths.pack("demo"), Path("/tmp/packs/demo"))
        self.assertEqual(paths.backup("demo.zip"), Path("/tmp/backups/demo.zip"))
        with self.assertRaises(ValueError):
            paths.pack("../outside")
        with self.assertRaises(ValueError):
            paths.backup("../outside.zip")

    def test_runtime_transfer_and_community_boundaries_delegate(self):
        class Backend:
            def list_installed_packs(self):
                return ["list"]

            def get_pack_detail(self, pack_id):
                return {"detail": pack_id}

            def set_default_pack(self, pack_id):
                return {"default": pack_id}

            def _create_empty_pack(self, pack_id):
                return {"created": pack_id}

            def inspect_pack_archive(self, path, suggested_pack_id=None):
                return {"inspect": path}

            def export_pack_archive(self, pack_id, **kwargs):
                return {"export": pack_id}

            def import_pack_archive(self, path, **kwargs):
                return {"import": path}

            def uninstall_pack(self, pack_id, **kwargs):
                return {"uninstall": pack_id}

            def fetch_and_cache_community_index(self, **kwargs):
                return {"community": True}

            def load_cached_community_index(self):
                return {"cached": True}

            def install_pack_from_github_source(self, source, **kwargs):
                return {"install": source}

        backend = Backend()
        self.assertEqual(PackRuntime(backend).list(), ["list"])
        self.assertEqual(PackRuntime(backend).detail("demo")["detail"], "demo")
        self.assertEqual(PackRuntime(backend).set_default("demo")["default"], "demo")
        self.assertEqual(PackRuntime(backend).create("demo")["created"], "demo")
        transfer = PackTransfer(backend)
        self.assertEqual(transfer.inspect("a.zip")["inspect"], "a.zip")
        self.assertEqual(transfer.export("demo")["export"], "demo")
        self.assertEqual(transfer.import_pack("a.zip")["import"], "a.zip")
        self.assertEqual(transfer.uninstall("demo")["uninstall"], "demo")
        community = CommunityPackSource(backend)
        self.assertEqual(community.fetch()["community"], True)
        self.assertEqual(community.cached()["cached"], True)
        self.assertEqual(community.install("owner/repo")["install"], "owner/repo")

    def test_runtime_create_rejects_invalid_pack_ids_before_calling_backend(self):
        class Backend:
            def _create_empty_pack(self, pack_id):
                raise AssertionError("invalid IDs must not reach the backend")

        runtime = PackRuntime(Backend())
        for pack_id in ("../outside", "/absolute", "bad id"):
            with self.subTest(pack_id=pack_id):
                with self.assertRaises(ValueError):
                    runtime.create(pack_id)

    def test_empty_pack_creation_is_bounded_to_the_configured_packs_root(self):
        with TemporaryDirectory() as temporary_directory:
            packs_root = Path(temporary_directory) / "packs"
            with patch.object(pack_storage, "PACKS_DIR", packs_root):
                self.assertEqual(pack_storage._create_empty_pack("valid-pack"), "valid-pack")
                self.assertTrue((packs_root / "valid-pack" / "manifest.json").is_file())
                for pack_id in ("../outside", "/absolute", "bad id"):
                    with self.subTest(pack_id=pack_id):
                        with self.assertRaises(ValueError):
                            pack_storage._create_empty_pack(pack_id)


if __name__ == "__main__":
    unittest.main()
