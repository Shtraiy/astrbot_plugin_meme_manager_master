import asyncio
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()


def _install_web_stubs() -> None:
    if "quart" in sys.modules:
        return

    class FakeRequest:
        def __init__(self):
            self.args = {}
            self.files = {}
            self.json_payload = {}

        async def get_json(self):
            return self.json_payload

    quart = types.ModuleType("quart")
    quart.request = FakeRequest()
    quart.jsonify = lambda payload: payload
    quart.send_file = lambda path: ("file", path)
    sys.modules["quart"] = quart

    werkzeug = types.ModuleType("werkzeug")
    exceptions = types.ModuleType("werkzeug.exceptions")
    exceptions.RequestEntityTooLarge = type("RequestEntityTooLarge", (Exception,), {})
    werkzeug.exceptions = exceptions
    sys.modules["werkzeug"] = werkzeug
    sys.modules["werkzeug.exceptions"] = exceptions

    utils = types.ModuleType("werkzeug.utils")
    utils.secure_filename = lambda value: str(value or "")
    werkzeug.utils = utils
    sys.modules["werkzeug.utils"] = utils


_install_web_stubs()

from quart import request  # noqa: E402

from meme_manager_master.backend import models  # noqa: E402
from meme_manager_master.backend.category_manager import CategoryManager  # noqa: E402
from meme_manager_master.backend.catalog_index_service import CatalogIndexService  # noqa: E402
from meme_manager_master.mixins import web_api  # noqa: E402
from meme_manager_master.mixins.web_api import WebAPIMixin  # noqa: E402


class Upload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.stream = io.BytesIO(content)


class AwaitableFiles(dict):
    def __await__(self):
        async def resolve():
            return self

        return resolve().__await__()


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(output, format="PNG")
    return output.getvalue()


class PackLocalManagementTests(unittest.TestCase):
    def _make_instance(self, root: Path) -> WebAPIMixin:
        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.catalog_index_service = CatalogIndexService(root)
        instance._default_pack_context = lambda: {
            "pack_id": "default-pack",
            "pack_dir": root / "packs" / "default-pack",
            "memes_dir": root / "packs" / "default-pack" / "memes",
        }
        instance._invalidate_default_pack_semantics = lambda: None
        instance.category_manager = types.SimpleNamespace(
            sync_with_filesystem=lambda: True,
        )
        return instance

    @staticmethod
    def _seed_pack(root: Path, pack_id: str) -> tuple[Path, str]:
        memes_dir = root / "packs" / pack_id / "memes"
        memes_dir.mkdir(parents=True)
        result = models.add_emoji_to_category(
            "happy", Upload("seed.png", png_bytes()), memes_dir
        )
        return memes_dir, result["filename"]

    @staticmethod
    def _set_json(payload: dict) -> None:
        async def get_json():
            return payload

        request.get_json = get_json

    def test_delete_from_selected_pack_does_not_touch_default_pack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, default_filename = self._seed_pack(root, "default-pack")
            _, selected_filename = self._seed_pack(root, "selected-pack")
            instance = self._make_instance(root)
            request.args = {"managed_pack_id": "selected-pack"}
            self._set_json({
                "category": "happy",
                "image_file": selected_filename,
            })

            with patch.object(web_api, "PACKS_DIR", root / "packs"):
                payload, status = asyncio.run(instance._api_delete_emoji())

            self.assertEqual(status, 200)
            self.assertTrue(
                (root / "packs" / "default-pack" / "memes" / default_filename).exists()
            )
            self.assertFalse(
                (root / "packs" / "selected-pack" / "memes" / selected_filename).exists()
            )
            self.assertEqual(payload["filename"], selected_filename)

    def test_invalid_selected_pack_is_rejected_without_default_mutation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, default_filename = self._seed_pack(root, "default-pack")
            instance = self._make_instance(root)
            request.args = {"managed_pack_id": "../outside"}
            self._set_json({
                "category": "happy",
                "image_file": default_filename,
            })

            with patch.object(web_api, "PACKS_DIR", root / "packs"):
                _payload, status = asyncio.run(instance._api_delete_emoji())

            self.assertEqual(status, 400)
            self.assertTrue(
                (root / "packs" / "default-pack" / "memes" / default_filename).exists()
            )

    def test_upload_from_selected_pack_writes_only_selected_pack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            default_memes = root / "packs" / "default-pack" / "memes"
            default_memes.mkdir(parents=True)
            selected_memes = root / "packs" / "selected-pack" / "memes"
            selected_memes.mkdir(parents=True)
            instance = self._make_instance(root)
            request.args = {"managed_pack_id": "selected-pack"}
            request.files = AwaitableFiles({"file": Upload("new.png", png_bytes())})

            with patch.object(web_api, "PACKS_DIR", root / "packs"):
                payload, status = asyncio.run(instance._api_add_emoji("happy"))

            self.assertEqual(status, 201)
            self.assertTrue((selected_memes / payload["filename"]).exists())
            self.assertFalse(list(default_memes.glob("meme_*")))

    def test_batch_move_and_clear_use_selected_pack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, default_filename = self._seed_pack(root, "default-pack")
            selected_memes, selected_filename = self._seed_pack(root, "selected-pack")
            instance = self._make_instance(root)

            request.args = {}
            self._set_json(
                {
                    "managed_pack_id": "selected-pack",
                    "source_category": "happy",
                    "target_category": "sad",
                    "image_files": [selected_filename],
                }
            )
            with patch.object(web_api, "PACKS_DIR", root / "packs"):
                payload, status = asyncio.run(instance._api_batch_move_emojis())

            self.assertEqual(status, 200)
            self.assertEqual(payload["moved_files"], [selected_filename])
            self.assertTrue(
                (root / "packs" / "default-pack" / "memes" / default_filename).exists()
            )

            self._set_json(
                {
                    "managed_pack_id": "selected-pack",
                    "category": "sad",
                }
            )
            with patch.object(web_api, "PACKS_DIR", root / "packs"):
                payload, status = asyncio.run(instance._api_clear_category())

            self.assertEqual(status, 200)
            self.assertEqual(payload["untagged_count"], 1)
            self.assertTrue((selected_memes / selected_filename).exists())

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

    def test_fixed_tag_ui_no_longer_calls_retired_category_mutations(self):
        emoji = Path("pages/a_manage/emoji.js").read_text(encoding="utf-8")
        pack = Path("pages/a_manage/pack.js").read_text(encoding="utf-8")
        script = Path("pages/a_manage/script.js").read_text(encoding="utf-8")
        self.assertNotIn('apiPost("category/rename"', emoji)
        self.assertNotIn('apiPost("category/delete"', emoji)
        self.assertNotIn('apiPost("category/restore"', pack)
        self.assertNotIn('apiPost("category/restore"', script)
        self.assertIn("managed_pack_id", emoji)


if __name__ == "__main__":
    unittest.main()
