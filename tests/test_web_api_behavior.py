import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()


def _install_web_stubs() -> None:
    """Stub quart/werkzeug/requests so the web mixins can be imported."""
    if "quart" in sys.modules:
        return

    class _FakeRequest:
        def __init__(self) -> None:
            self.args = {}
            self.method = "GET"
            self.content_length = None
            self.files = {}

        async def get_json(self):
            return {}

    quart = types.ModuleType("quart")
    quart.request = _FakeRequest()
    quart.jsonify = lambda payload: payload
    quart.send_file = lambda path: ("file", path)
    sys.modules["quart"] = quart

    werkzeug = types.ModuleType("werkzeug")
    exceptions = types.ModuleType("werkzeug.exceptions")
    exceptions.RequestEntityTooLarge = type(
        "RequestEntityTooLarge", (Exception,), {}
    )
    werkzeug.exceptions = exceptions
    sys.modules["werkzeug"] = werkzeug
    sys.modules["werkzeug.exceptions"] = exceptions

    utils = types.ModuleType("werkzeug.utils")
    utils.secure_filename = lambda value: str(value or "")
    werkzeug.utils = utils
    sys.modules["werkzeug.utils"] = utils

    requests = types.ModuleType("requests")
    sys.modules["requests"] = requests


_install_web_stubs()

from meme_manager_master.mixins.web_api import WebAPIMixin  # noqa: E402
from meme_manager_master.mixins import emoji_api  # noqa: E402
from meme_manager_master.mixins import pack_api  # noqa: E402
from meme_manager_master.mixins import web_api  # noqa: E402


class WebApiBehaviorTests(unittest.TestCase):
    def test_bound_webui_response_status_helper_accepts_response(self):
        instance = WebAPIMixin.__new__(WebAPIMixin)
        self.assertEqual(instance._get_webui_response_status(({}, 201)), 201)

    def test_bound_upload_helper_supports_sync_and_async_save(self):
        class SyncUpload:
            def save(self, destination):
                Path(destination).write_bytes(b"sync")

        class AsyncUpload:
            async def save(self, destination):
                Path(destination).write_bytes(b"async")

        instance = WebAPIMixin.__new__(WebAPIMixin)
        with tempfile.TemporaryDirectory() as temp_dir:
            sync_path = Path(temp_dir) / "sync.zip"
            async_path = Path(temp_dir) / "async.zip"
            asyncio_run(instance._save_uploaded_file(SyncUpload(), sync_path))
            asyncio_run(instance._save_uploaded_file(AsyncUpload(), async_path))
            self.assertEqual(sync_path.read_bytes(), b"sync")
            self.assertEqual(async_path.read_bytes(), b"async")

    def test_bound_pack_import_session_helper_validates_token(self):
        instance = WebAPIMixin.__new__(WebAPIMixin)
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(web_api, "TEMP_DIR", Path(temp_dir)):
                archive_path, metadata_path = instance._pack_import_session_paths(
                    "a" * 32
                )
                self.assertEqual(archive_path.name, "".join(["a"] * 32) + ".zip")
                self.assertEqual(metadata_path.suffix, ".json")
                with self.assertRaises(ValueError):
                    instance._pack_import_session_paths("invalid")

    def test_runtime_backup_base64_decoder_enforces_archive_limit(self):
        with self.assertRaises(ValueError):
            pack_api._decode_bounded_base64("A" * 100, limit=8)

    def test_export_result_does_not_expose_local_archive_path(self):
        result = pack_api._public_export_result(
            {
                "archive_path": r"C:\\private\\backup.zip",
                "archive_filename": "backup.zip",
            }
        )
        self.assertNotIn("archive_path", result)
        self.assertEqual(result["archive_filename"], "backup.zip")

    def test_invalid_webui_upload_returns_bad_request(self):
        from quart import request

        class AwaitableFiles(dict):
            def __await__(self):
                async def resolve():
                    return self

                return resolve().__await__()

        request.files = AwaitableFiles(
            {"file": types.SimpleNamespace(filename="fake.png")}
        )
        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.category_manager = types.SimpleNamespace(sync_with_filesystem=lambda: None)

        async def run_mutation(_operation, mutate):
            return mutate()

        instance._run_default_pack_mutation = run_mutation
        original = emoji_api.add_emoji_to_category
        emoji_api.add_emoji_to_category = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("上传文件不是有效图片")
        )
        try:
            _payload, status = asyncio_run(instance._api_add_emoji("happy"))
        finally:
            emoji_api.add_emoji_to_category = original
        self.assertEqual(status, 400)

    def test_get_emojis_without_managed_pack_does_not_raise_binding_error(self):
        from quart import request

        async def scan_default_folder():
            return {"happy": ["smile.png"]}

        original_scan = emoji_api.scan_emoji_folder
        emoji_api.scan_emoji_folder = scan_default_folder
        try:
            request.args = {}
            instance = WebAPIMixin.__new__(WebAPIMixin)
            payload = asyncio_run(instance._api_get_emojis())
        finally:
            emoji_api.scan_emoji_folder = original_scan

        self.assertEqual(payload, {"happy": ["smile.png"]})

    def test_get_emojis_from_managed_pack_returns_images(self):
        from quart import request

        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "demo"
            category_dir = pack_dir / "memes" / "happy"
            category_dir.mkdir(parents=True)
            (category_dir / "smile.png").write_bytes(b"image")
            request.args = {"managed_pack_id": "demo"}
            instance = WebAPIMixin.__new__(WebAPIMixin)
            with patch.object(web_api, "PACKS_DIR", Path(temp_dir)):
                payload = asyncio_run(instance._api_get_emojis())

        self.assertEqual(payload, {"happy": ["smile.png"]})

    def _make_instance(self, memes_root: Path) -> WebAPIMixin:
        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance._resolve_webui_pack_view_context = lambda: {
            "memes_dir": memes_root,
        }
        instance._default_pack_context = lambda: {
            "memes_dir": memes_root,
        }
        instance._safe_image_filename = lambda name: bool(
            name and Path(name).name == name and name not in {".", ".."}
        )
        return instance

    def test_invalid_category_returns_400(self):
        from quart import request

        with tempfile.TemporaryDirectory() as temp_dir:
            instance = self._make_instance(Path(temp_dir))
            request.args = {"category": "../outside", "filename": "a.png"}
            payload, status = asyncio_run(instance._api_serve_meme_image())
            self.assertEqual(status, 400)
            self.assertIn("message", payload)

    def test_missing_file_returns_404(self):
        from quart import request

        with tempfile.TemporaryDirectory() as temp_dir:
            instance = self._make_instance(Path(temp_dir))
            request.args = {"category": "happy", "filename": "ghost.png"}
            payload, status = asyncio_run(instance._api_serve_meme_image())
            self.assertEqual(status, 404)
            self.assertIn("message", payload)

    def test_image_data_rejects_missing_file_without_missing_helper_error(self):
        from quart import request

        with tempfile.TemporaryDirectory() as temp_dir:
            instance = WebAPIMixin.__new__(WebAPIMixin)
            instance._default_pack_context = lambda: {
                "memes_dir": Path(temp_dir),
            }
            request.args = {"category": "happy", "filename": "ghost.png"}
            payload, status = asyncio_run(instance._api_get_meme_image_data())

        self.assertEqual(status, 404)
        self.assertIn("message", payload)

    def test_image_data_helpers_build_raw_and_thumbnail_data_urls(self):
        from PIL import Image

        instance = WebAPIMixin.__new__(WebAPIMixin)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "preview.png"
            Image.new("RGBA", (4, 4), (20, 120, 80, 255)).save(image_path)

            raw_url = instance._build_file_data_url(image_path, "image/png")
            preview_url, preview_mime = instance._build_preview_data_url(image_path)

        self.assertTrue(raw_url.startswith("data:image/png;base64,"))
        self.assertTrue(preview_url.startswith("data:image/webp;base64,"))
        self.assertEqual(preview_mime, "image/webp")

    def test_oversized_preview_returns_413(self):
        from quart import request

        with tempfile.TemporaryDirectory() as temp_dir:
            memes_root = Path(temp_dir)
            category_dir = memes_root / "happy"
            category_dir.mkdir()
            big_file = category_dir / "big.png"
            with big_file.open("wb") as handle:
                handle.truncate(33 * 1024 * 1024)
            instance = self._make_instance(memes_root)
            request.args = {"category": "happy", "filename": "big.png"}
            payload, status = asyncio_run(instance._api_get_meme_image_data())
            self.assertEqual(status, 413)
            self.assertNotIn(str(memes_root), str(payload))

    def test_error_payload_does_not_leak_absolute_path(self):
        from quart import request

        with tempfile.TemporaryDirectory() as temp_dir:
            instance = self._make_instance(Path(temp_dir))
            request.args = {"category": "happy", "filename": "ghost.png"}
            _payload, status = asyncio_run(instance._api_serve_meme_image())
            self.assertEqual(status, 404)


def asyncio_run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
