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


class Upload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.stream = io.BytesIO(content)


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(output, format="PNG")
    return output.getvalue()


class ModelsUploadSecurityTests(unittest.TestCase):
    def test_rejects_fake_image_without_creating_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                models.add_emoji_to_category(
                    "happy",
                    Upload("fake.png", b"not an image"),
                    Path(temp_dir),
                )
            self.assertEqual(list(Path(temp_dir).rglob("*")), [])

    def test_rejects_upload_larger_than_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            oversized = b"0" * (models.MAX_UPLOAD_IMAGE_BYTES + 1)
            with self.assertRaises(ValueError):
                models.add_emoji_to_category(
                    "happy",
                    Upload("large.png", oversized),
                    Path(temp_dir),
                )
            self.assertEqual(list(Path(temp_dir).rglob("*")), [])

    def test_valid_image_is_saved_with_no_temp_file_left(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = models.add_emoji_to_category(
                "happy",
                Upload("valid.png", png_bytes()),
                Path(temp_dir),
            )
            saved = Path(result["path"])
            self.assertTrue(saved.is_file())
            self.assertEqual(saved.read_bytes(), png_bytes())
            self.assertFalse(any(path.name.endswith(".tmp") for path in saved.parent.iterdir()))


if __name__ == "__main__":
    unittest.main()
