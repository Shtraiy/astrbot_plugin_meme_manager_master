import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.pack_repository import PackRepository, pack_lock


PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _make_repo(root: Path) -> PackRepository:
    repo = PackRepository(root)
    category_dir = repo.memes_dir / "happy"
    category_dir.mkdir(parents=True)
    (category_dir / "a.png").write_bytes(PNG_1PX)
    (root / "memes_data.json").write_text(
        json.dumps({"happy": "开心"}, ensure_ascii=False),
        encoding="utf-8",
    )
    return repo


class PackRepositoryRollbackTests(unittest.TestCase):
    def test_rename_category_rolls_back_dir_and_metadata_when_save_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_repo(Path(temp_dir))
            with patch(
                "backend.pack_repository.atomic_write_json",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaises(OSError):
                    repo.rename_category("happy", "joy")
            self.assertTrue((repo.memes_dir / "happy" / "a.png").is_file())
            self.assertFalse((repo.memes_dir / "joy").exists())
            self.assertEqual(
                json.loads(repo.metadata_path.read_text(encoding="utf-8")),
                {"happy": "开心"},
            )

    def test_delete_category_restores_from_trash_when_save_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_repo(Path(temp_dir))
            with patch(
                "backend.pack_repository.atomic_write_json",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaises(OSError):
                    repo.delete_category("happy")
            self.assertTrue((repo.memes_dir / "happy" / "a.png").is_file())
            self.assertEqual(
                json.loads(repo.metadata_path.read_text(encoding="utf-8")),
                {"happy": "开心"},
            )
            self.assertEqual(list(repo.trash_dir.rglob("*")), [])

    def test_replace_image_invalid_extension_keeps_old_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_repo(Path(temp_dir))
            with self.assertRaises(ValueError):
                repo.replace_image("happy", "a.png", "b.txt", PNG_1PX)
            self.assertTrue((repo.memes_dir / "happy" / "a.png").is_file())
            self.assertFalse((repo.memes_dir / "happy" / "b.txt").exists())

    def test_replace_image_write_failure_keeps_old_image_and_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_repo(Path(temp_dir))
            with patch(
                "backend.pack_repository.os.replace",
                side_effect=OSError("io error"),
            ):
                with self.assertRaises(OSError):
                    repo.replace_image("happy", "a.png", "b.png", PNG_1PX)
            self.assertTrue((repo.memes_dir / "happy" / "a.png").is_file())
            self.assertFalse((repo.memes_dir / "happy" / "b.png").exists())
            self.assertEqual(
                list((repo.memes_dir / "happy").glob(".*.tmp")),
                [],
            )

    def test_replace_image_success_uses_atomic_replace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_repo(Path(temp_dir))
            target = repo.replace_image("happy", "a.png", "b.png", PNG_1PX)
            self.assertEqual(target.name, "b.png")
            self.assertEqual((repo.memes_dir / "happy" / "b.png").read_bytes(), PNG_1PX)
            self.assertFalse((repo.memes_dir / "happy" / "a.png").exists())
            catalog = json.loads(
                (repo.memes_dir / "happy" / "index.json").read_text(encoding="utf-8")
            )
            self.assertIn("b.png", {item.get("filename") for item in catalog["items"]})


class PackRepositoryBatchTests(unittest.TestCase):
    def test_move_images_reports_success_missing_conflict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_repo(Path(temp_dir))
            (repo.memes_dir / "sad").mkdir()
            (repo.memes_dir / "sad" / "x.png").write_bytes(PNG_1PX)
            (repo.memes_dir / "happy" / "x.png").write_bytes(PNG_1PX)
            result = repo.move_images("happy", "sad", ["a.png", "x.png", "nope.png", "a.png"])
            self.assertEqual(result.succeeded, ("a.png",))
            self.assertEqual(set(result.missing), {"nope.png"})
            self.assertEqual(result.conflicting, ("x.png",))
            self.assertTrue((repo.memes_dir / "sad" / "a.png").is_file())
            self.assertFalse((repo.memes_dir / "happy" / "a.png").exists())

    def test_copy_images_reports_success_and_conflict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_repo(Path(temp_dir))
            (repo.memes_dir / "sad").mkdir()
            (repo.memes_dir / "sad" / "z.png").write_bytes(PNG_1PX)
            result = repo.copy_images("happy", "sad", ["a.png", "missing.png"])
            self.assertEqual(result.succeeded, ("a.png",))
            self.assertEqual(result.missing, ("missing.png",))
            self.assertEqual(result.conflicting, ())
            self.assertTrue((repo.memes_dir / "happy" / "a.png").is_file())
            self.assertTrue((repo.memes_dir / "sad" / "a.png").is_file())

    def test_delete_images_removes_only_present_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _make_repo(Path(temp_dir))
            result = repo.delete_images("happy", ["a.png", "ghost.png"])
            self.assertEqual(result.succeeded, ("a.png",))
            self.assertEqual(result.missing, ("ghost.png",))
            self.assertFalse((repo.memes_dir / "happy" / "a.png").exists())

    def test_pack_lock_is_stable_per_pack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir)
            self.assertIs(pack_lock(pack_dir), pack_lock(pack_dir))
            self.assertIsNot(pack_lock(pack_dir), pack_lock(Path(temp_dir) / "other"))


if __name__ == "__main__":
    unittest.main()
