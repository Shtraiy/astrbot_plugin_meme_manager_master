import io
import subprocess
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
    def test_upload_save_path_runs_without_astrbot_installed(self):
        script = r'''
import io, sys, tempfile, types
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path.cwd().parent))
werkzeug = types.ModuleType("werkzeug")
utils = types.ModuleType("werkzeug.utils")
utils.secure_filename = lambda value: str(value or "")
werkzeug.utils = utils
sys.modules["werkzeug"] = werkzeug
sys.modules["werkzeug.utils"] = utils
from astrbot_plugin_meme_manager_master.backend.models import add_emoji_to_category
payload = io.BytesIO()
Image.new("RGB", (1, 1), "blue").save(payload, "PNG")
class Upload:
    filename = "smoke.png"
    stream = io.BytesIO(payload.getvalue())
with tempfile.TemporaryDirectory() as root:
    result = add_emoji_to_category("happy", Upload(), Path(root))
    assert Path(result["path"]).is_file()
assert "astrbot" not in sys.modules
'''
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

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
