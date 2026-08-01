import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.pack_repository import PackRepository


PNG = b"\x89PNG\r\n\x1a\nplaceholder"


def _make_big_repo(root: Path, category_count: int = 50, images_per_category: int = 20) -> PackRepository:
    repo = PackRepository(root)
    for index in range(category_count):
        category_dir = repo.memes_dir / f"cat{index:02d}"
        category_dir.mkdir(parents=True)
        for image_index in range(images_per_category):
            (category_dir / f"img{image_index:02d}.png").write_bytes(PNG)
    return repo


class BatchReconcileTests(unittest.TestCase):
    def test_batch_move_reconciles_once_with_source_and_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_big_repo(Path(temp_dir))
            with patch("storage.MemeStore.reconcile_categories", return_value=0) as reconcile:
                result = repo.move_images(
                    "cat00",
                    "newcat",
                    [f"img{index:02d}.png" for index in range(20)],
                )
            self.assertEqual(len(result.succeeded), 20)
            reconcile.assert_called_once()
            categories = reconcile.call_args.args[0]
            self.assertEqual(set(categories), {"cat00", "newcat"})

    def test_batch_delete_reconciles_once_with_source_category(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_big_repo(Path(temp_dir))
            with patch("storage.MemeStore.reconcile_categories", return_value=0) as reconcile:
                result = repo.delete_images(
                    "cat00", [f"img{index:02d}.png" for index in range(20)]
                )
            self.assertEqual(len(result.succeeded), 20)
            reconcile.assert_called_once()
            self.assertEqual(set(reconcile.call_args.args[0]), {"cat00"})

    def test_batch_copy_reconciles_once_with_source_and_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_big_repo(Path(temp_dir))
            with patch("storage.MemeStore.reconcile_categories", return_value=0) as reconcile:
                result = repo.copy_images(
                    "cat00",
                    "newcat",
                    [f"img{index:02d}.png" for index in range(20)],
                )
            self.assertEqual(len(result.succeeded), 20)
            reconcile.assert_called_once()
            self.assertEqual(set(reconcile.call_args.args[0]), {"cat00", "newcat"})

    def test_batch_move_never_triggers_full_library_reconcile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_big_repo(Path(temp_dir))
            with patch("storage.MemeStore.reconcile_catalogs") as full_reconcile, patch(
                "storage.MemeStore.reconcile_category", return_value=False
            ) as category_reconcile:
                result = repo.move_images(
                    "cat00",
                    "newcat",
                    [f"img{index:02d}.png" for index in range(20)],
                )
            self.assertEqual(len(result.succeeded), 20)
            full_reconcile.assert_not_called()
            self.assertEqual(category_reconcile.call_count, 2)
            categories = {call.args[0] for call in category_reconcile.call_args_list}
            self.assertEqual(categories, {"cat00", "newcat"})


if __name__ == "__main__":
    unittest.main()
