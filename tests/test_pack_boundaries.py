import unittest
from pathlib import Path

from backend.community_pack_source import CommunityPackSource
from backend.pack_backup import PackBackup
from backend.pack_paths import PackPaths
from backend.pack_runtime import PackRuntime
from backend.pack_transfer import PackTransfer


class PackBoundaryTests(unittest.TestCase):
    def test_pack_paths_keep_pack_and_backup_targets_bounded(self):
        paths = PackPaths(Path("/tmp/packs"), Path("/tmp/backups"))
        self.assertEqual(paths.pack("demo"), Path("/tmp/packs/demo"))
        self.assertEqual(paths.backup("demo.zip"), Path("/tmp/backups/demo.zip"))
        with self.assertRaises(ValueError):
            paths.pack("../outside")
        with self.assertRaises(ValueError):
            paths.backup("../outside.zip")

    def test_runtime_transfer_backup_and_community_boundaries_delegate(self):
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

            def export_runtime_backup(self, **kwargs):
                return {"backup": True}

            def import_runtime_backup(self, path, **kwargs):
                return {"restore": path}

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
        self.assertEqual(PackBackup(backend).export()["backup"], True)
        self.assertEqual(PackBackup(backend).import_backup("a.zip")["restore"], "a.zip")
        community = CommunityPackSource(backend)
        self.assertEqual(community.fetch()["community"], True)
        self.assertEqual(community.cached()["cached"], True)
        self.assertEqual(community.install("owner/repo")["install"], "owner/repo")


if __name__ == "__main__":
    unittest.main()
