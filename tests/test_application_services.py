import unittest
from pathlib import Path

from application.services import (
    CaptureService,
    CatalogService,
    CommunityPackService,
    PackService,
    PackBackupService,
    PackRuntimeService,
    SelectionApplicationService,
    PackTransferService,
)
from domain.models import Category, MemeId, PackContext, PackId, SelectionResult


class ApplicationServiceTests(unittest.TestCase):
    def test_pack_application_facades_keep_runtime_backup_and_community_contracts(self):
        legacy = type(
            "LegacyPackStorage",
            (),
            {
                "list_installed_packs": lambda _: ["demo"],
                "get_pack_detail": lambda _, pack_id: {"pack_id": pack_id},
                "set_default_pack": lambda _, pack_id: {"default": pack_id},
                "export_runtime_backup": lambda _, **kwargs: {"backup": True},
                "import_runtime_backup": lambda _, path, **kwargs: {"restore": path},
                "fetch_and_cache_community_index": lambda _, **kwargs: {"community": True},
                "load_cached_community_index": lambda _: {"cached": True},
                "find_cached_pack_entry": lambda _, pack_id: {"id": pack_id},
                "install_pack_from_github_source": lambda _, source, **kwargs: {
                    "install": source
                },
                "install_first_official_pack_from_index": lambda _, **kwargs: {
                    "official": True
                },
            },
        )()
        self.assertEqual(PackRuntimeService(legacy).list(), ["demo"])
        self.assertEqual(PackRuntimeService(legacy).detail("demo")["pack_id"], "demo")
        self.assertEqual(PackBackupService(legacy).export()["backup"], True)
        self.assertEqual(PackBackupService(legacy).restore("backup.zip")["restore"], "backup.zip")
        community = CommunityPackService(legacy)
        self.assertEqual(community.fetch()["community"], True)
        self.assertEqual(community.cached()["cached"], True)
        self.assertEqual(community.find_cached("demo")["id"], "demo")
        self.assertEqual(community.install({"repo": "owner/repo"})["install"], {"repo": "owner/repo"})
        self.assertTrue(community.install_official_first(index_url="https://example.test/index.json")["official"])

    def test_pack_transfer_service_exposes_stable_operation_names(self):
        legacy = type(
            "LegacyPackStorage",
            (),
            {
                "inspect_pack_archive": lambda _, path, suggested_pack_id=None: {"path": path},
                "export_pack_archive": lambda _, pack_id, **kwargs: {"pack_id": pack_id},
                "uninstall_pack": lambda _, pack_id, **kwargs: {"pack_id": pack_id},
            },
        )()
        service = PackTransferService(legacy)
        self.assertEqual(service.inspect("a.zip")["path"], "a.zip")
        self.assertEqual(service.export("demo")["pack_id"], "demo")
        self.assertEqual(service.uninstall("demo")["pack_id"], "demo")

    def test_pack_service_delegates_resolution(self):
        expected = PackContext(PackId("demo"), Path("/tmp/demo"), Path("/tmp"))
        service = PackService(type("Resolver", (), {"resolve": lambda _, value: expected})())
        self.assertIs(service.resolve("demo"), expected)

    def test_catalog_service_returns_repository_report(self):
        report = {"changed": True, "items": 2}
        repository = type("Catalog", (), {"reconcile": lambda _, pack: report})()
        service = CatalogService(repository)
        self.assertEqual(service.reconcile(object()), report)

    def test_selection_service_normalizes_mapping_result(self):
        service = SelectionApplicationService(
            chooser=lambda request: {
                "selected_id": "image-1",
                "category": "happy",
                "confidence": 0.7,
                "reason": "scene",
            }
        )
        result = service.choose({"text": "hello"})
        self.assertEqual(result, SelectionResult(MemeId("image-1"), Category("happy"), 0.7, "scene"))

    def test_capture_service_keeps_processor_outside_event_adapter(self):
        seen = []
        service = CaptureService(processor=lambda request: seen.append(request) or {"saved": 1})
        self.assertEqual(service.handle({"source": "message"}), {"saved": 1})
        self.assertEqual(seen, [{"source": "message"}])


if __name__ == "__main__":
    unittest.main()
