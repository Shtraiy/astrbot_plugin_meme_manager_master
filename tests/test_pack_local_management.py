import io
import sys
import tempfile
import types
import unittest
from pathlib import Path

from PIL import Image

from tests.fakes import install_package_alias, install_runtime_stubs


def _install_werkzeug_stub() -> None:
    if "werkzeug" in sys.modules:
        return
    werkzeug = types.ModuleType("werkzeug")
    utils = types.ModuleType("werkzeug.utils")
    utils.secure_filename = lambda value: str(value or "")
    werkzeug.utils = utils
    sys.modules["werkzeug"] = werkzeug
    sys.modules["werkzeug.utils"] = utils


install_runtime_stubs()
install_package_alias()
_install_werkzeug_stub()

from meme_manager_master.backend import models
from meme_manager_master.backend.category_manager import CategoryManager
from storage import MemeStore


class Upload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.stream = io.BytesIO(content)


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(output, format="PNG")
    return output.getvalue()


class PackLocalManagementTests(unittest.TestCase):
    @staticmethod
    def _seed_pack(root: Path, pack_id: str) -> tuple[Path, str]:
        pack_dir = root / "packs" / pack_id
        memes_dir = pack_dir / "memes"
        memes_dir.mkdir(parents=True)
        (pack_dir / "manifest.json").write_text("{}", encoding="utf-8")
        result = models.add_emoji_to_category(
            "happy", Upload("seed.png", png_bytes()), memes_dir
        )
        return memes_dir, result["filename"]

    def test_delete_last_selected_item_keeps_catalog_manifest_consistent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected_memes, selected_filename = self._seed_pack(root, "selected-pack")
            store = MemeStore(root / "packs" / "selected-pack")

            removed = models.delete_emoji_from_category(
                "happy", selected_filename, selected_memes
            )

            self.assertTrue(removed)
            self.assertFalse((selected_memes / selected_filename).exists())
            self.assertEqual(store.load_catalog().get("items"), [])
            self.assertTrue(
                (root / "packs" / "selected-pack" / "manifest.json").is_file()
            )

    def test_category_manager_can_update_selected_pack_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "selected-pack"
            (pack_dir / "memes").mkdir(parents=True)
            manager = CategoryManager(pack_dir)

            self.assertTrue(manager.update_description("happy", "Selected pack"))
            self.assertIn("Selected pack", manager.get_descriptions().values())
            self.assertEqual(
                (pack_dir / "memes_data.json").read_text(encoding="utf-8").count(
                    "Selected pack"
                ),
                1,
            )
            self.assertTrue((pack_dir / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
