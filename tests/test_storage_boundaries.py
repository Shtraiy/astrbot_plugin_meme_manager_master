import ast
import tempfile
import threading
import unittest
from pathlib import Path

from infrastructure.catalog_repository import CatalogLock, CatalogRepository
from infrastructure.image_repository import ImageRepository
from infrastructure.selection_state import SelectionState
from infrastructure.storage_policy import (
    is_safe_category_segment,
    resolve_safe_category_dir,
    safe_extension,
)


ROOT = Path(__file__).parents[1]


def _definition_count(name: str) -> int:
    tree = ast.parse((ROOT / "storage.py").read_text(encoding="utf-8"))
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in tree.body
    )


class StorageBoundaryTests(unittest.TestCase):
    def test_storage_policy_compatibility_names_have_one_definition(self):
        for name in ("is_safe_category_segment", "resolve_safe_category_dir", "_safe_extension"):
            self.assertEqual(_definition_count(name), 1, name)

    def test_storage_policy_rejects_escape_and_normalizes_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.assertTrue(is_safe_category_segment("happy"))
            self.assertFalse(is_safe_category_segment("../outside"))
            self.assertEqual(resolve_safe_category_dir(root, "happy"), root / "happy")
            with self.assertRaises(ValueError):
                resolve_safe_category_dir(root, "../outside")
        self.assertEqual(safe_extension("JPEG"), ".jpg")
        self.assertEqual(safe_extension(".unknown"), ".png")

    def test_catalog_repository_preserves_legacy_catalog_shapes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = CatalogRepository(Path(temp_dir) / "pack")
            repository.write([{"filename": "meme.png", "tags": ["happy"]}])
            self.assertEqual(repository.load()["items"][0]["filename"], "meme.png")

            index = Path(temp_dir) / "pack" / "memes" / "index.json"
            index.write_text('{"images": {"old.png": {"description": "legacy"}}}', encoding="utf-8")
            self.assertEqual(repository.load()["items"][0]["filename"], "old.png")

    def test_catalog_lock_serializes_threads_for_one_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "catalog.lock"
            entered = []
            barrier = threading.Barrier(2)

            def worker(marker):
                barrier.wait()
                with CatalogLock(lock_path):
                    entered.append(marker)

            threads = [threading.Thread(target=worker, args=(item,)) for item in (1, 2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(sorted(entered), [1, 2])

    def test_image_and_selection_boundaries_delegate_without_changing_result_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "pack"
            images = ImageRepository(root)
            saved = images.save(b"boundary-image", ["happy"])
            self.assertEqual(saved.status, "saved")
            self.assertTrue(saved.path.is_file())
            selection = SelectionState(root)
            self.assertEqual(selection.pick(tags=["happy"]), saved.path)


if __name__ == "__main__":
    unittest.main()
