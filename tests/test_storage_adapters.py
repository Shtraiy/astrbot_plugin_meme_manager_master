import tempfile
import unittest
from pathlib import Path

from domain.models import PackContext, PackId
from infrastructure.storage_adapters import MemeStoreCatalogRepository, MemeStoreImageRepository


class StorageAdapterTests(unittest.TestCase):
    def test_catalog_adapter_returns_structured_reconcile_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = PackContext(PackId("demo"), root / "demo", root)
            adapter = MemeStoreCatalogRepository()
            report = adapter.reconcile(context)
            self.assertEqual(report["pack_id"], "demo")
            self.assertIn("changed", report)

    def test_image_adapter_delegates_save_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = MemeStoreImageRepository(Path(temp_dir))
            result = adapter.save(b"not-a-real-image", ["happy"])
            self.assertEqual(result.status, "saved")
            self.assertTrue(result.path.is_file())


if __name__ == "__main__":
    unittest.main()
