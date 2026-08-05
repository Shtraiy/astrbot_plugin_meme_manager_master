import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()


if "quart" not in sys.modules:
    quart = types.ModuleType("quart")

    class _Request:
        args = {}

        async def get_json(self):
            return {}

    quart.request = _Request()
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
    sys.modules["requests"] = types.ModuleType("requests")

from capture_activity import record_capture_event
from meme_manager_master.mixins import capture_index_api
from meme_manager_master.mixins.capture_index_api import CaptureIndexAPIMixin
from meme_manager_master.backend.catalog_index_service import CatalogIndexService
from storage import MemeStore


class CaptureIndexApiTests(unittest.TestCase):
    def test_workspace_returns_recent_indexed_and_pending_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            indexed = store.save_image(b"indexed-image", "happy", ".png").path
            pending = store.save_image(b"pending-image", "happy", ".png").path
            catalog = store.load_catalog("happy")
            for item in catalog["items"]:
                if item["filename"] == indexed.name:
                    item["indexed"] = True
                else:
                    item["indexed"] = False
            store.write_catalog(
                "happy",
                catalog["items"],
                {"classification_index_complete": False},
            )
            record_capture_event(
                pack_dir,
                category="happy",
                filename=pending.name,
                digest=store.image_digest(pending),
                status="pending",
                captured_at=200,
            )

            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance._library_index_state = {"status": "idle"}
            instance._safe_image_filename = lambda value: Path(value).suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
            }
            instance.store = store

            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent):
                workspace = instance._capture_workspace_for_pack("pack")

        self.assertEqual(workspace["summary"]["indexed"], 1)
        self.assertEqual(workspace["summary"]["pending"], 1)
        self.assertEqual(workspace["indexed_items"][0]["filename"], indexed.name)
        self.assertEqual(workspace["pending_items"][0]["filename"], pending.name)

    def test_workspace_does_not_expose_absolute_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            image = store.save_image(b"image", "happy", ".png").path
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance._library_index_state = {}
            instance._safe_image_filename = lambda value: True
            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent):
                workspace = instance._capture_workspace_for_pack("pack")

        serialized = json.dumps(workspace, ensure_ascii=False)
        self.assertNotIn(str(pack_dir), serialized)
        self.assertIn(f"memes/{image.name}", serialized)

    def test_workspace_can_filter_items_by_category(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            happy = store.save_image(b"happy-image", "happy", ".png").path
            sad = store.save_image(b"sad-image", "sad", ".png").path
            catalog = store.load_catalog("happy")
            catalog["items"][0]["indexed"] = True
            store.write_catalog("happy", catalog["items"])

            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance._library_index_state = {}
            instance._safe_image_filename = lambda value: True
            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent):
                workspace = instance._capture_workspace_for_pack("pack", "happy")

        self.assertEqual({item["category"] for item in workspace["indexed_items"]}, {"开心"})
        self.assertEqual({item["category"] for item in workspace["pending_items"]}, set())
        self.assertEqual({folder["category"] for folder in workspace["folders"]}, {"开心", "悲伤"})
        self.assertEqual(workspace["summary"]["indexed"], 1)
        self.assertEqual(workspace["summary"]["pending"], 0)
        self.assertEqual(workspace["summary"]["folder_total"], 1)

    def test_reindex_pack_updates_filenames_without_model_work(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            category_dir = store.memes_dir / "happy"
            category_dir.mkdir(parents=True)
            (category_dir / "happy_0001.png").write_bytes(b"first")
            (category_dir / "happy_0003.png").write_bytes(b"third")
            store.write_catalog(
                "happy",
                [
                    {"filename": "happy_0001.png", "indexed": True},
                    {
                        "filename": "happy_0003.png",
                        "indexed": True,
                        "description": "保留",
                    },
                ],
            )

            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent):
                result = instance._reindex_pack_catalog("pack")

                self.assertEqual(result["category_count"], 1)
                self.assertEqual(result["changed_file_count"], 2)
                catalog = MemeStore(pack_dir).load_catalog()
                filenames = {item["filename"] for item in catalog["items"]}
                self.assertEqual(len(filenames), 2)
                self.assertTrue(all(name.startswith("meme_") for name in filenames))
                self.assertEqual(
                    next(item for item in catalog["items"] if item.get("description"))["description"],
                    "保留",
                )


class ManualIndexApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_index_queues_task_before_returning_to_the_page(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance.store = store
            instance._library_task = None
            instance._library_index_state = {"status": "completed", "message": "旧状态"}
            instance._library_completed_key = ("old", ())
            instance._library_retry_key = None
            instance._library_retry_at = 0.0
            instance._capture_pack_id = lambda data=None: str((data or {}).get("pack_id") or "pack")
            instance._ensure_library_index = AsyncMock()
            instance._log_library_task_failure = lambda task: None

            class Request:
                async def get_json(self):
                    return {"pack_id": "pack"}

            with (
                patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent),
                patch.object(capture_index_api, "request", Request()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
            ):
                response = await instance._api_capture_index()

            self.assertEqual(response[1], 202)
            self.assertEqual(instance._library_index_state["status"], "queued")
            await instance._library_task


class ManualIndexStatusApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_index_status_returns_current_snapshot_without_workspace_scan(self):
        instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
        instance._capture_pack_id = lambda data=None: "pack"
        instance._library_index_state = {
            "status": "running",
            "processed": 1147,
            "total": 1149,
            "classified": 2,
            "errors": 0,
            "message": "正在请求视觉模型：批次 1/1（2 张）",
        }

        class Request:
            args = {"pack_id": "pack"}

        with (
            patch.object(capture_index_api, "request", Request()),
            patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
        ):
            result = await instance._api_capture_index_status()

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["processed"], 1147)
        self.assertEqual(result["message"], "正在请求视觉模型：批次 1/1（2 张）")

    async def test_index_status_returns_idle_snapshot_when_not_started(self):
        instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
        instance._capture_pack_id = lambda data=None: "pack"
        instance._library_index_state = {}

        class Request:
            args = {"pack_id": "pack"}

        with (
            patch.object(capture_index_api, "request", Request()),
            patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
        ):
            result = await instance._api_capture_index_status()

        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["pack_id"], "pack")


class ReindexProgressApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_reindex_reports_running_progress_then_completed_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            store.save_image(b"first", "happy", ".png")
            store.save_image(b"second", "sad", ".png")

            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance.catalog_index_service = CatalogIndexService(pack_dir.parent)
            instance._capture_pack_id = lambda data=None: "pack"

            class _Request:
                args = {}

                async def get_json(self):
                    return {"pack_id": "pack"}

            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent), patch.object(
                capture_index_api, "request", _Request()
            ):
                started = await instance._api_capture_reindex()
                self.assertEqual(started["status"], "running")
                self.assertEqual(started["total"], 2)
                await instance._reindex_tasks["pack"]
                finished = await instance._api_capture_reindex_status()

        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["processed"], 2)
        self.assertEqual(finished["total"], 2)

    async def test_reindex_task_failure_is_exposed_in_state(self):
        instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)

        class FailingCatalogService:
            async def run_locked_pack_mutation(self, *args, **kwargs):
                raise RuntimeError("catalog exploded")

        instance.catalog_index_service = FailingCatalogService()
        state = {
            "pack_id": "pack",
            "status": "running",
            "processed": 0,
            "total": 0,
            "changed_file_count": 0,
            "message": "running",
        }

        await instance._run_reindex_task("pack", state)

        self.assertEqual(state["status"], "error")
        self.assertIn("catalog exploded", state["message"])

    async def test_reindex_rejects_duplicate_running_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            pack_dir.mkdir(parents=True)
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance._capture_pack_id = lambda data=None: "pack"
            instance._reindex_states = {
                "pack": {
                    "pack_id": "pack",
                    "status": "running",
                    "processed": 1,
                    "total": 2,
                    "changed_file_count": 0,
                    "message": "running",
                }
            }
            instance._library_task = None
            never_finished = asyncio.create_task(asyncio.Event().wait())
            instance._reindex_tasks = {"pack": never_finished}

            class _Request:
                args = {}

                async def get_json(self):
                    return {"pack_id": "pack"}

            try:
                with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent), patch.object(
                    capture_index_api, "request", _Request()
                ), patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload):
                    response = await instance._api_capture_reindex()
            finally:
                never_finished.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await never_finished

        self.assertEqual(response[1], 409)
        self.assertEqual(response[0]["status"], "running")

    async def test_zero_file_pack_reindex_completes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            pack_dir.mkdir(parents=True)
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance.catalog_index_service = CatalogIndexService(pack_dir.parent)
            instance._capture_pack_id = lambda data=None: "pack"

            class _Request:
                args = {}

                async def get_json(self):
                    return {"pack_id": "pack"}

            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent), patch.object(
                capture_index_api, "request", _Request()
            ), patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload):
                started = await instance._api_capture_reindex()
                await instance._reindex_tasks["pack"]

        self.assertEqual(started["status"], "running")
        self.assertEqual(instance._reindex_states["pack"]["status"], "completed")
        self.assertEqual(instance._reindex_states["pack"]["processed"], 0)
        self.assertEqual(instance._reindex_states["pack"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
