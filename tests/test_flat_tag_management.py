import io
import sys
import tempfile
import types
import unittest
from pathlib import Path

from PIL import Image

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

if "werkzeug" not in sys.modules:
    werkzeug = types.ModuleType("werkzeug")
    utils = types.ModuleType("werkzeug.utils")
    utils.secure_filename = lambda value: str(value or "")
    werkzeug.utils = utils
    sys.modules["werkzeug"] = werkzeug
    sys.modules["werkzeug.utils"] = utils

from meme_manager_master.backend import models  # noqa: E402
from meme_manager_master.storage import MemeStore  # noqa: E402


class Upload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.stream = io.BytesIO(content)


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "green").save(output, format="PNG")
    return output.getvalue()


class FlatTagManagementTests(unittest.TestCase):
    def test_upload_uses_stable_flat_name_and_normalized_tag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memes_dir = Path(temp_dir) / "memes"
            result = models.add_emoji_to_category(
                "happy", Upload("original.png", png_bytes()), memes_dir
            )

            self.assertRegex(result["filename"], r"^meme_[0-9a-f]{12}\.png$")
            self.assertEqual(Path(result["path"]).parent, memes_dir)
            self.assertFalse((memes_dir / "happy").exists())
            entry = MemeStore(memes_dir.parent).load_catalog()["items"][0]
            self.assertEqual(entry["tags"], ["开心"])

    def test_copy_adds_tag_without_creating_a_second_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memes_dir = Path(temp_dir) / "memes"
            uploaded = models.add_emoji_to_category(
                "happy", Upload("original.png", png_bytes()), memes_dir
            )
            result = models.copy_emoji_to_category(
                "happy", uploaded["filename"], "surprised", memes_dir
            )

            self.assertTrue(result["copied"])
            self.assertEqual(len(list(memes_dir.glob("meme_*"))), 1)
            entry = MemeStore(memes_dir.parent).load_catalog()["items"][0]
            self.assertEqual(entry["tags"], ["开心", "震惊"])

    def test_scan_and_get_return_virtual_tag_buckets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memes_dir = Path(temp_dir) / "memes"
            uploaded = models.add_emoji_to_category(
                "happy", Upload("original.png", png_bytes()), memes_dir
            )
            models.copy_emoji_to_category(
                "happy", uploaded["filename"], "surprised", memes_dir
            )

            scanned = self._run(models.scan_emoji_folder(memes_dir))
            self.assertEqual(scanned["开心"], [uploaded["filename"]])
            self.assertEqual(scanned["震惊"], [uploaded["filename"]])
            self.assertEqual(models.get_emoji_by_category("surprised", memes_dir), [uploaded["filename"]])

    @staticmethod
    def _run(awaitable):
        import asyncio

        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
