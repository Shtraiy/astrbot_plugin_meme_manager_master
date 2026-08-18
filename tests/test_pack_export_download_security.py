import asyncio
import json
import sys
import tempfile
import time
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

from meme_manager_master.mixins import pack_api  # noqa: E402
from meme_manager_master.mixins.pack_api import PackAPIMixin  # noqa: E402
from meme_manager_master.mixins.web_api import WebAPIMixin  # noqa: E402
from meme_manager_master.mixins.web_routes import enabled_route_specs  # noqa: E402


def _async_json(payload: dict):
    async def get_json():
        return payload

    return get_json


class PackExportDownloadSecurityTests(unittest.TestCase):
    def test_route_specs_use_post_prepare_and_get_download(self):
        specs = {
            spec.path: spec for spec in enabled_route_specs({"core"})
        }
        self.assertEqual(specs["packs/export/prepare"].methods, ("POST",))
        self.assertEqual(specs["packs/export/download"].methods, ("GET",))
        self.assertNotEqual(
            specs["packs/export/download"].handler_name,
            "_api_download_pack",
        )
        self.assertNotIn(
            "_api_download_pack",
            {
                spec.handler_name
                for spec in enabled_route_specs({"core", "catalog_index"})
            },
        )

    def test_export_session_paths_validates_token(self):
        instance = PackAPIMixin.__new__(PackAPIMixin)
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(pack_api, "TEMP_DIR", Path(temp_dir)):
                archive_path, metadata_path = instance._pack_export_session_paths(
                    "b" * 32
                )
                self.assertEqual(archive_path.name, "".join(["b"] * 32) + ".zip")
                self.assertEqual(metadata_path.name, "".join(["b"] * 32) + ".json")
                with self.assertRaises(ValueError):
                    instance._pack_export_session_paths("invalid")

    def test_prepare_is_registered_as_mutating_route(self):
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
            return {"prepared": True}

        instance._register_webui_api(
            "packs/export/prepare", mutation, ["POST"], "test"
        )
        response = asyncio.run(registered[0][1]())
        self.assertEqual(response[1], 401)

    def test_prepare_creates_token_session_without_absolute_path(self):
        from quart import request

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            backup_root = temp_root / "backup"
            backup_root.mkdir()
            archive = backup_root / "made.zip"
            archive.write_bytes(b"zip-content")
            instance = PackAPIMixin.__new__(PackAPIMixin)

            async def guarded(*args, **kwargs):
                return {
                    "archive_path": str(archive),
                    "archive_filename": "pack.zip",
                }

            instance._run_guarded_pack_file_operation = guarded
            request.get_json = _async_json(
                {"pack_id": "p", "mode": "share"}
            )
            with patch.object(pack_api, "TEMP_DIR", temp_root / "tmp"):
                with patch.object(pack_api, "BACKUP_DIR", backup_root):
                    payload, status = asyncio.run(instance._api_pack_export_prepare())

            self.assertEqual(status, 200)
            token = payload["download_token"]
            self.assertEqual(len(token), 32)
            self.assertNotIn(str(temp_root), str(payload))
            session_dir = temp_root / "tmp" / "pack_export_sessions"
            self.assertTrue((session_dir / f"{token}.json").is_file())
            self.assertTrue(archive.exists())

    def test_download_rejects_missing_and_invalid_tokens(self):
        from quart import request

        instance = PackAPIMixin.__new__(PackAPIMixin)
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(pack_api, "TEMP_DIR", Path(temp_dir)):
                request.args = {}
                payload, status = asyncio.run(instance._api_pack_export_download())
                self.assertEqual(status, 400)
                self.assertIn("凭证", payload["message"])

                request.args = {"token": "not-hex"}
                payload, status = asyncio.run(instance._api_pack_export_download())
                self.assertEqual(status, 400)
                self.assertIn("凭证", payload["message"])

    def test_download_rejects_expired_session(self):
        from quart import request

        instance = PackAPIMixin.__new__(PackAPIMixin)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            backup_root = temp_root / "backup"
            backup_root.mkdir()
            archive = backup_root / "pack.zip"
            archive.write_bytes(b"zip")
            session_dir = temp_root / "pack_export_sessions"
            session_dir.mkdir(parents=True)
            token = "c" * 32
            (session_dir / f"{token}.json").write_text(
                json.dumps(
                    {
                        "pack_id": "p",
                        "mode": "share",
                        "archive_path": str(archive),
                        "archive_filename": "pack.zip",
                        "created_at": time.time(),
                        "expires_at": time.time() - 10,
                    }
                ),
                encoding="utf-8",
            )
            request.args = {"token": token}
            with patch.object(pack_api, "TEMP_DIR", temp_root):
                with patch.object(pack_api, "BACKUP_DIR", backup_root):
                    payload, status = asyncio.run(instance._api_pack_export_download())

            self.assertEqual(status, 400)
            self.assertIn("过期", payload["message"])

    def test_download_valid_token_sends_file_and_cleans_up(self):
        from quart import request

        class FakeResponse:
            def __init__(self) -> None:
                self.cleaned_up = False

            def call_on_close(self, callback):
                callback()
                self.cleaned_up = True

        instance = PackAPIMixin.__new__(PackAPIMixin)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            backup_root = temp_root / "backup"
            backup_root.mkdir()
            archive = backup_root / "pack.zip"
            archive.write_bytes(b"zip")
            session_dir = temp_root / "pack_export_sessions"
            session_dir.mkdir(parents=True)
            token = "d" * 32
            metadata_path = session_dir / f"{token}.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "pack_id": "p",
                        "mode": "share",
                        "archive_path": str(archive),
                        "archive_filename": "pack.zip",
                        "created_at": time.time(),
                        "expires_at": time.time() + 60,
                    }
                ),
                encoding="utf-8",
            )
            request.args = {"token": token}
            sent = []
            response = FakeResponse()

            async def fake_send_file(*args, **kwargs):
                sent.append((args, kwargs))
                return response

            with patch.object(pack_api, "TEMP_DIR", temp_root):
                with patch.object(pack_api, "BACKUP_DIR", backup_root):
                    with patch.object(pack_api, "send_file", fake_send_file):
                        result = asyncio.run(instance._api_pack_export_download())

            self.assertIs(result, response)
            self.assertEqual(sent[0][0][0], archive)
            self.assertEqual(
                sent[0][1]["attachment_filename"],
                "pack.zip",
            )
            self.assertTrue(response.cleaned_up)
            self.assertFalse(metadata_path.exists())
            self.assertTrue(archive.exists())

    def test_get_pack_detail_strips_absolute_pack_dir(self):
        instance = PackAPIMixin.__new__(PackAPIMixin)
        with patch.object(
            pack_api,
            "get_pack_detail",
            return_value={
                "id": "p",
                "pack_dir": "/srv/data/packs/p",
                "manifest": {"name": "p"},
                "total_images": 0,
            },
        ):
            payload = asyncio.run(instance._api_get_pack_detail("p"))

        self.assertNotIn("pack_dir", payload)
        self.assertNotIn("/srv/data/packs/p", str(payload))
        self.assertEqual(payload["id"], "p")


if __name__ == "__main__":
    unittest.main()
