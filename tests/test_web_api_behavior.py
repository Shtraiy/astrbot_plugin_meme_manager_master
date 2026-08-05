import asyncio
import sys
import tempfile
import threading
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
    def test_registered_mutation_rejects_missing_authentication_context(self):
        from quart import request

        request.method = "POST"
        request.username = None
        request.headers = {
            "Host": "localhost:6185",
            "Origin": "http://localhost:6185",
        }
        registered = []
        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.context = types.SimpleNamespace(
            register_web_api=lambda *args: registered.append(args)
        )

        async def mutation():
            return {"mutated": True}

        instance._register_webui_api("mutation", mutation, ["POST"], "test")
        response = asyncio_run(registered[0][1]())
        status = response[1] if isinstance(response, tuple) else None

        self.assertEqual(status, 401)

    def test_registered_mutation_rejects_cross_origin_request(self):
        from quart import request

        request.method = "POST"
        request.username = "admin"
        request.headers = {
            "Host": "localhost:6185",
            "Origin": "https://attacker.example",
        }
        registered = []
        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.context = types.SimpleNamespace(
            register_web_api=lambda *args: registered.append(args)
        )

        async def mutation():
            return {"mutated": True}

        instance._register_webui_api("mutation", mutation, ["POST"], "test")
        response = asyncio_run(registered[0][1]())
        status = response[1] if isinstance(response, tuple) else None

        self.assertEqual(status, 403)

    def test_registered_mutation_allows_authenticated_same_origin_request(self):
        from quart import request

        request.method = "POST"
        request.username = "admin"
        request.headers = {
            "Host": "localhost:6185",
            "Origin": "http://localhost:6185",
        }
        registered = []
        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.context = types.SimpleNamespace(
            register_web_api=lambda *args: registered.append(args)
        )

        async def mutation():
            return {"mutated": True}

        instance._register_webui_api("mutation", mutation, ["POST"], "test")
        payload = asyncio_run(registered[0][1]())

        self.assertEqual(payload, {"mutated": True})

    def test_registered_mutation_rejects_missing_origin_evidence(self):
        from quart import request

        request.method = "POST"
        request.username = "admin"
        request.headers = {"Host": "localhost:6185"}
        registered = []
        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.context = types.SimpleNamespace(
            register_web_api=lambda *args: registered.append(args)
        )

        async def mutation():
            return {"mutated": True}

        instance._register_webui_api("mutation", mutation, ["POST"], "test")
        response = asyncio_run(registered[0][1]())

        self.assertEqual(response[1], 403)

    def test_registered_read_does_not_require_mutation_security_context(self):
        from quart import request

        request.method = "GET"
        request.username = None
        request.headers = {}
        registered = []
        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.context = types.SimpleNamespace(
            register_web_api=lambda *args: registered.append(args)
        )

        async def read_only():
            return {"read": True}

        instance._register_webui_api("read-only", read_only, ["GET"], "test")

        self.assertEqual(asyncio_run(registered[0][1]()), {"read": True})

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

    def test_community_routes_use_composition_root_service(self):
        class Community:
            def fetch(self, **kwargs):
                return {"fetched_at": "now", "source_url": kwargs["index_url"], "index": {"packs": [{"id": "demo"}]}}

            def cached(self):
                return {"fetched_at": "cached", "source_url": "cache", "index": {"packs": []}}

            def find_cached(self, pack_id):
                return {"id": pack_id, "source": {"repo": "owner/repo"}}

            def install(self, source, **kwargs):
                return {"pack_id": "demo", "source": source}

            def install_official_first(self, **kwargs):
                return {"pack_id": "official-demo"}

        async def get_json():
            return {"pack_id": "demo", "set_as_default": True}

        async def run_guarded(_operation, function, *args, **kwargs):
            return function(*args, **kwargs)

        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.community_pack_service = Community()
        instance._get_github_accelerator_url = lambda: ""
        instance._run_guarded_runtime_file_operation = run_guarded
        instance._reload_personas = lambda: None
        from quart import request

        request.get_json = get_json
        fetched, fetched_status = asyncio_run(instance._api_fetch_community_index())
        cached, cached_status = asyncio_run(instance._api_get_cached_community_index())
        installed, install_status = asyncio_run(instance._api_install_community_pack())
        request.get_json = lambda: _async_value({"set_as_default": True})
        official, official_status = asyncio_run(instance._api_install_official_first_pack())

        self.assertEqual((fetched_status, cached_status, install_status, official_status), (200, 200, 200, 200))
        self.assertEqual(fetched["source_url"], web_api.COMMUNITY_INDEX_URL)
        self.assertEqual(cached["fetched_at"], "cached")
        self.assertEqual(installed["pack_id"], "demo")
        self.assertEqual(official["pack_id"], "official-demo")

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

        self.assertEqual(len(payload), 1)
        tag, filenames = next(iter(payload.items()))
        self.assertEqual(tag, "开心")
        self.assertEqual(len(filenames), 1)
        self.assertTrue(filenames[0].startswith("meme_"))

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

    def test_guarded_runtime_pack_mutation_refreshes_active_capture_store(self):
        """Catch import, install, or restore succeeding while capture keeps an old pack."""
        events = []

        class Guard:
            def begin_external_pack_operation(self, pack_id, operation):
                events.append(("begin", pack_id, operation))

            def end_external_pack_operation(self, pack_id):
                events.append(("end", pack_id))

        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.catalog_index_service = Guard()
        instance._refresh_store_for_active_pack = lambda: events.append(("refresh",))

        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir = Path(temp_dir) / "packs"
            (packs_dir / "before").mkdir(parents=True)
            result = asyncio_run(
                _run_guarded_runtime_mutation(instance, packs_dir)
            )

        self.assertEqual(result, {"pack_id": "after"})
        self.assertIn(("refresh",), events)

    def test_guarded_pack_mutation_refreshes_active_capture_store(self):
        """Catch overwrite import or uninstall changing the default behind capture."""
        events = []

        class Guard:
            def begin_external_pack_operation(self, pack_id, operation):
                events.append(("begin", pack_id, operation))

            def end_external_pack_operation(self, pack_id):
                events.append(("end", pack_id))

        instance = WebAPIMixin.__new__(WebAPIMixin)
        instance.catalog_index_service = Guard()
        instance._refresh_store_for_active_pack = lambda: events.append(("refresh",))

        result = asyncio_run(
            instance._run_guarded_pack_file_operation(
                "default-pack",
                "overwrite pack",
                lambda **_kwargs: {"switched_default_to": "after"},
            )
        )

        self.assertEqual(result, {"switched_default_to": "after"})
        self.assertIn(("refresh",), events)

    def test_cancelled_runtime_mutation_refreshes_store_after_worker_finishes(self):
        """Catch a cancelled backup restore that leaves capture on the old pack."""
        events = []
        instance = _guarded_operation_instance(events)

        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir = Path(temp_dir) / "packs"
            (packs_dir / "before").mkdir(parents=True)
            cancelled = asyncio_run(
                _cancel_guarded_runtime_mutation(instance, packs_dir)
            )

        self.assertTrue(cancelled)
        self.assertIn(("refresh",), events)

    def test_cancelled_pack_mutation_refreshes_store_after_worker_finishes(self):
        """Catch a cancelled overwrite import that leaves capture on the old pack."""
        events = []
        instance = _guarded_operation_instance(events)

        cancelled = asyncio_run(_cancel_guarded_pack_mutation(instance))

        self.assertTrue(cancelled)
        self.assertIn(("refresh",), events)


async def _run_guarded_runtime_mutation(instance, packs_dir):
    with patch.object(web_api, "PACKS_DIR", packs_dir):
        return await instance._run_guarded_runtime_file_operation(
            "install pack",
            lambda **_kwargs: {"pack_id": "after"},
        )


def _guarded_operation_instance(events):
    class Guard:
        def begin_external_pack_operation(self, pack_id, operation):
            events.append(("begin", pack_id, operation))

        def end_external_pack_operation(self, pack_id):
            events.append(("end", pack_id))

    instance = WebAPIMixin.__new__(WebAPIMixin)
    instance.catalog_index_service = Guard()
    instance._refresh_store_for_active_pack = lambda: events.append(("refresh",))
    return instance


async def _cancel_guarded_runtime_mutation(instance, packs_dir):
    with patch.object(web_api, "PACKS_DIR", packs_dir):
        return await _cancel_guarded_operation(
            instance._run_guarded_runtime_file_operation,
            "restore backup",
        )


async def _cancel_guarded_pack_mutation(instance):
    return await _cancel_guarded_operation(
        lambda operation, function: instance._run_guarded_pack_file_operation(
            "default-pack", operation, function
        ),
        "overwrite pack",
    )


async def _cancel_guarded_operation(run_operation, operation):
    worker_started = threading.Event()
    worker_completed = threading.Event()

    def mutation(**_kwargs):
        worker_started.set()
        worker_completed.wait()
        return {"pack_id": "after"}

    task = asyncio.create_task(run_operation(operation, mutation))
    await asyncio.to_thread(worker_started.wait)
    task.cancel()
    worker_completed.set()
    try:
        await task
    except asyncio.CancelledError:
        return True
    return False


async def _async_value(value):
    return value


def asyncio_run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
