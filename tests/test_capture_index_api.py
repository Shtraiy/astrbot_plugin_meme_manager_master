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

from capture_activity import load_capture_activity, mark_capture_events_ignored, record_capture_event
from capture_blacklist import CaptureBlacklist
from meme_manager_master.mixins import capture_index_api
from meme_manager_master.mixins.capture_index_api import CaptureIndexAPIMixin
from meme_manager_master.backend.catalog_index_service import CatalogIndexService
from storage import MemeStore


class CaptureIndexApiTests(unittest.TestCase):
    def test_workspace_merges_tags_and_paginates_unique_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            first = store.save_image(b"multi-tag-image", ["happy", "sad"], ".png").path
            for index in range(50):
                store.save_image(f"image-{index}".encode(), "happy", ".png")
            pending = store.save_image(b"pending-image", "happy", ".png").path
            catalog = store.load_catalog()
            for item in catalog["items"]:
                item["indexed"] = item["filename"] != pending.name
            store.write_catalog(catalog["items"])

            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance._library_index_state = {"status": "idle"}
            instance.store = store

            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent):
                first_page = instance._capture_workspace_for_pack("pack", page=1)
                second_page = instance._capture_workspace_for_pack("pack", page=2)
                clamped_page = instance._capture_workspace_for_pack("pack", page=99)
                filtered = instance._capture_workspace_for_pack("pack", "sad", page=1)

        self.assertEqual(first_page["pagination"]["page"], 1)
        self.assertEqual(first_page["pagination"]["page_size"], 48)
        self.assertEqual(first_page["pagination"]["indexed"]["total"], 51)
        self.assertEqual(first_page["pagination"]["indexed"]["total_pages"], 2)
        self.assertEqual(first_page["pagination"]["pending"]["total"], 1)
        self.assertEqual(first_page["pagination"]["pending"]["total_pages"], 1)
        self.assertEqual(len(first_page["indexed_items"]), 48)
        self.assertEqual(len(first_page["pending_items"]), 1)
        self.assertEqual(len(second_page["indexed_items"]), 3)
        self.assertEqual(len(second_page["pending_items"]), 1)
        self.assertEqual(clamped_page["pagination"]["page"], 2)
        self.assertEqual(len(clamped_page["indexed_items"]), 3)
        self.assertEqual(first_page["summary"]["indexed"], 51)
        self.assertEqual(len(filtered["indexed_items"]), 1)
        self.assertEqual(filtered["indexed_items"][0]["filename"], first.name)
        self.assertEqual(set(filtered["indexed_items"][0]["tags"]), {"开心", "悲伤"})

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

    def test_workspace_hides_ignored_duplicates_and_exposes_digest_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            image = store.save_image(b"duplicate-image", "happy", ".png").path
            digest = store.image_digest(image)
            record_capture_event(
                pack_dir,
                category="happy",
                filename=image.name,
                digest=digest,
                status="duplicate",
            )

            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance._library_index_state = {}
            instance._safe_image_filename = lambda value: True
            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent):
                before = instance._capture_workspace_for_pack("pack")
                self.assertEqual(before["summary"]["duplicate"], 1)
                self.assertEqual(before["duplicate_digests"], [digest])
                mark_capture_events_ignored(pack_dir, digests={digest})
                after = instance._capture_workspace_for_pack("pack")

        self.assertEqual(after["summary"]["duplicate"], 0)
        self.assertFalse(any(item.get("duplicate") for item in after["pending_items"]))
        self.assertEqual(after["duplicate_digests"], [])


class IgnoreDuplicateApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_ignore_endpoint_marks_all_matching_events_without_deleting_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            image = store.save_image(b"duplicate-image", "happy", ".png").path
            digest = store.image_digest(image)
            record_capture_event(
                pack_dir,
                category="happy",
                filename=image.name,
                digest=digest,
                status="duplicate",
            )
            record_capture_event(
                pack_dir,
                category="sad",
                filename=image.name,
                digest=digest,
                status="duplicate",
            )
            catalog_before = store.load_catalog("happy")
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance.store = store
            instance.capture_blacklist = CaptureBlacklist(Path(temp_dir) / "plugin-data")
            instance._capture_pack_id = CaptureIndexAPIMixin._capture_pack_id.__get__(instance)

            class Request:
                args = {}

                async def get_json(self):
                    return {"pack_id": "pack", "sha256s": [digest, digest]}

            with (
                patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent),
                patch.object(capture_index_api, "request", Request()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
            ):
                response = await instance._api_capture_ignore_duplicates()

            self.assertEqual(
                response,
                {"message": "已忽略重复记录并加入黑名单", "ignored": 2, "blacklisted_count": 1},
            )
            self.assertTrue(image.is_file())
            self.assertEqual(store.load_catalog("happy"), catalog_before)
            self.assertEqual(
                {event["status"] for event in capture_index_api.load_capture_activity(pack_dir)["events"]},
                {"ignored"},
            )
            self.assertTrue(instance.capture_blacklist.contains(digest))

    async def test_ignore_endpoint_rejects_invalid_digest_and_inactive_pack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            pack_dir.mkdir()
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance.store = MemeStore(pack_dir)
            instance.capture_blacklist = CaptureBlacklist(Path(temp_dir) / "plugin-data")
            instance._capture_pack_id = CaptureIndexAPIMixin._capture_pack_id.__get__(instance)

            class Request:
                args = {}

                async def get_json(self):
                    return {"pack_id": "pack", "sha256s": ["not-a-sha256"]}

            with (
                patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent),
                patch.object(capture_index_api, "request", Request()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
            ):
                response = await instance._api_capture_ignore_duplicates()

            self.assertEqual(response[1], 400)

            instance.store = MemeStore(pack_dir.parent / "other")
            class InactiveRequest(Request):
                async def get_json(self):
                    return {"pack_id": "pack", "sha256s": ["a" * 64]}

            with (
                patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent),
                patch.object(capture_index_api, "request", InactiveRequest()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
            ):
                response = await instance._api_capture_ignore_duplicates()

            self.assertEqual(response[1], 409)


class DisposeCaptureItemsTests(unittest.IsolatedAsyncioTestCase):
    def _fixture(self, temporary: str):
        packs_dir = Path(temporary) / "packs"
        pack_dir = packs_dir / "pack"
        store = MemeStore(pack_dir)
        indexed = store.save_image(b"indexed", "happy", ".png").path
        pending = store.save_image(b"pending", "sad", ".png").path
        duplicate = store.save_image(b"existing duplicate", "happy", ".png").path
        catalog = store.load_catalog()
        for item in catalog["items"]:
            item["indexed"] = item["filename"] != pending.name
        store.write_catalog(catalog["items"])
        pending_digest = store.image_digest(pending)
        duplicate_digest = store.image_digest(duplicate)
        record_capture_event(
            pack_dir,
            category="sad",
            filename=pending.name,
            digest=pending_digest,
            status="pending",
        )
        record_capture_event(
            pack_dir,
            category="happy",
            filename=duplicate.name,
            digest=duplicate_digest,
            status="duplicate",
        )
        instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
        instance.store = store
        instance.catalog_index_service = CatalogIndexService(packs_dir.parent)
        instance.capture_blacklist = CaptureBlacklist(Path(temporary) / "plugin-data")
        return instance, packs_dir, store, indexed, pending, duplicate, duplicate_digest

    async def test_dispose_endpoint_deletes_indexed_and_pending_but_keeps_duplicate_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            instance, packs_dir, store, indexed, pending, duplicate, duplicate_digest = self._fixture(temporary)
            instance.catalog_index_service = CatalogIndexService(packs_dir.parent)
            instance._capture_pack_id = lambda data=None: "pack"

            class Request:
                async def get_json(self):
                    return {
                        "pack_id": "pack",
                        "items": [
                            {"kind": "indexed", "filename": indexed.name},
                            {"kind": "pending", "filename": pending.name},
                            {"kind": "duplicate", "sha256": duplicate_digest},
                        ],
                    }

            with (
                patch.object(capture_index_api, "PACKS_DIR", packs_dir),
                patch.object(capture_index_api, "request", Request()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
            ):
                response = await instance._api_capture_dispose_items()

            self.assertEqual(response["disposed_count"], 3)
            self.assertEqual(response["failed"], [])
            self.assertFalse(indexed.exists())
            self.assertFalse(pending.exists())
            self.assertTrue(duplicate.exists())
            self.assertNotIn(indexed.name, {item["filename"] for item in store.load_catalog()["items"]})
            self.assertNotIn(pending.name, {item["filename"] for item in store.load_catalog()["items"]})
            statuses = {event["sha256"]: event["status"] for event in load_capture_activity(store.root)["events"]}
            self.assertEqual(statuses[store.image_digest(duplicate)], "ignored")
            self.assertEqual(set(instance.capture_blacklist.load()), {
                capture_index_api.hashlib.sha256(b"indexed").hexdigest(),
                capture_index_api.hashlib.sha256(b"pending").hexdigest(),
                duplicate_digest,
            })

    async def test_blacklist_write_failure_prevents_all_disposal(self):
        with tempfile.TemporaryDirectory() as temporary:
            instance, packs_dir, _store, indexed, pending, duplicate, _digest = self._fixture(temporary)
            instance._capture_pack_id = lambda data=None: "pack"

            class FailingBlacklist:
                def add(self, _digests):
                    raise OSError("disk full")

            instance.capture_blacklist = FailingBlacklist()

            class Request:
                async def get_json(self):
                    return {"pack_id": "pack", "items": [{"kind": "indexed", "filename": indexed.name}]}

            with (
                patch.object(capture_index_api, "PACKS_DIR", packs_dir),
                patch.object(capture_index_api, "request", Request()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
            ):
                response = await instance._api_capture_dispose_items()

            self.assertEqual(response[1], 500)
            self.assertIn("黑名单", response[0]["message"])
            self.assertTrue(indexed.exists())
            self.assertTrue(pending.exists())
            self.assertTrue(duplicate.exists())

    async def test_delete_failure_is_reported_as_blacklisted_and_retry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            instance, packs_dir, _store, indexed, _pending, _duplicate, _digest = self._fixture(temporary)
            instance._capture_pack_id = lambda data=None: "pack"

            class Request:
                async def get_json(self):
                    return {
                        "pack_id": "pack",
                        "items": [{"kind": "indexed", "filename": indexed.name}],
                    }

            original_unlink = Path.unlink

            def fail_indexed_unlink(path, *args, **kwargs):
                if path == indexed:
                    raise OSError("locked")
                return original_unlink(path, *args, **kwargs)

            with (
                patch.object(capture_index_api, "PACKS_DIR", packs_dir),
                patch.object(capture_index_api, "request", Request()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
                patch.object(Path, "unlink", fail_indexed_unlink),
            ):
                response = await instance._api_capture_dispose_items()

            self.assertEqual(response["disposed_count"], 0)
            self.assertEqual(response["failed_count"], 1)
            self.assertTrue(response["failed"][0]["blacklisted"])
            self.assertTrue(indexed.exists())
            self.assertTrue(instance.capture_blacklist.contains(
                capture_index_api.hashlib.sha256(b"indexed").hexdigest()
            ))

            with (
                patch.object(capture_index_api, "PACKS_DIR", packs_dir),
                patch.object(capture_index_api, "request", Request()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
            ):
                first = await instance._api_capture_dispose_items()
                second = await instance._api_capture_dispose_items()

            self.assertEqual(first["disposed_count"], 1)
            self.assertEqual(second["disposed_count"], 0)
            self.assertEqual(second["failed_count"], 1)

    async def test_dispose_endpoint_rejects_invalid_items_and_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            instance, packs_dir, _store, _indexed, _pending, _duplicate, _digest = self._fixture(temporary)
            instance._capture_pack_id = lambda data=None: "pack"
            payloads = [
                {"pack_id": "pack", "items": [{"kind": "pending", "filename": "../escape.png"}]},
                {"pack_id": "pack", "items": [{"kind": "unknown", "filename": "x.png"}]},
                {"pack_id": "pack", "items": [{"kind": "duplicate", "sha256": "a" * 64}] * 501},
            ]

            for payload in payloads:
                class Request:
                    async def get_json(self):
                        return payload

                with (
                    patch.object(capture_index_api, "PACKS_DIR", packs_dir),
                    patch.object(capture_index_api, "request", Request()),
                    patch.object(capture_index_api, "jsonify", side_effect=lambda value: value),
                ):
                    response = await instance._api_capture_dispose_items()
                self.assertEqual(response[1], 400)

    async def test_ignore_all_endpoint_ignores_pending_and_duplicate_items_pack_wide(self):
        with tempfile.TemporaryDirectory() as temporary:
            instance, packs_dir, store, _indexed, pending, duplicate, duplicate_digest = self._fixture(
                temporary
            )
            instance._capture_pack_id = lambda data=None: "pack"
            pending_digest = store.image_digest(pending)

            class Request:
                async def get_json(self):
                    return {"pack_id": "pack"}

            with (
                patch.object(capture_index_api, "PACKS_DIR", packs_dir),
                patch.object(capture_index_api, "request", Request()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
            ):
                response = await instance._api_capture_ignore_all_items()

            self.assertEqual(response["ignored_count"], 2)
            self.assertEqual(response["disposed_count"], 1)
            self.assertFalse(pending.exists())
            self.assertTrue(duplicate.exists())
            statuses = {
                event["sha256"]: event["status"]
                for event in load_capture_activity(store.root)["events"]
            }
            self.assertEqual(statuses[pending_digest], "ignored")
            self.assertEqual(statuses[duplicate_digest], "ignored")
            self.assertTrue(instance.capture_blacklist.contains(pending_digest))
            self.assertTrue(instance.capture_blacklist.contains(duplicate_digest))

class ReindexPackTests(unittest.TestCase):
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

    async def test_manual_index_only_queues_selected_pending_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            pending = store.save_image(b"selected-pending", "happy", ".png").path
            untouched = store.save_image(b"untouched-pending", "sad", ".png").path
            duplicate = store.save_image(b"duplicate-item", "happy", ".png").path
            duplicate_digest = store.image_digest(duplicate)
            record_capture_event(
                pack_dir,
                category="happy",
                filename=duplicate.name,
                digest=duplicate_digest,
                status="duplicate",
            )
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance.store = store
            instance.catalog_index_service = CatalogIndexService(pack_dir.parent)
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
                    return {
                        "pack_id": "pack",
                        "items": [
                            {
                                "kind": "pending",
                                "filename": pending.name,
                                "sha256": store.image_digest(pending),
                            },
                            {"kind": "pending", "filename": untouched.name, "sha256": "0" * 64},
                            {"kind": "duplicate", "sha256": duplicate_digest},
                        ],
                    }

            with (
                patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent),
                patch.object(capture_index_api, "request", Request()),
                patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
            ):
                response = await instance._api_capture_index()

            self.assertEqual(response[1], 202)
            await instance._library_task
            selected = instance._ensure_library_index.await_args.kwargs["selected_filenames"]
            self.assertEqual(selected, {pending.name})


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
    async def test_reindex_status_restores_persisted_running_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            pack_dir.mkdir(parents=True)
            persisted = {
                "pack_id": "pack",
                "status": "running",
                "processed": 1,
                "total": 3,
                "changed_file_count": 0,
                "classified": 1,
                "skipped": 0,
                "reindexed": 1,
                "errors": 0,
                "message": "正在请求视觉模型：批次 1/3",
            }
            (pack_dir / "reindex_state.json").write_text(
                json.dumps(persisted, ensure_ascii=False),
                encoding="utf-8",
            )
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance._capture_pack_id = lambda data=None: "pack"
            instance._reindex_states = {}
            instance._reindex_tasks = {}
            resume_started = asyncio.Event()
            keep_running = asyncio.Event()

            async def resume(pack_id, state):
                self.assertEqual(pack_id, "pack")
                self.assertEqual(state["processed"], 1)
                resume_started.set()
                await keep_running.wait()

            instance._run_reindex_task = resume

            class Request:
                args = {"pack_id": "pack"}

            try:
                with (
                    patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent),
                    patch.object(capture_index_api, "request", Request()),
                    patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
                ):
                    result = await instance._api_capture_reindex_status()
                await asyncio.wait_for(resume_started.wait(), timeout=1)
            finally:
                keep_running.set()
                tasks = list(instance._reindex_tasks.values())
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["total"], 3)

    async def test_reindex_reports_running_progress_then_completed_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            store.save_image(b"first", "happy", ".png")
            store.save_image(b"second", "sad", ".png")

            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance.catalog_index_service = CatalogIndexService(pack_dir.parent)
            instance._capture_pack_id = lambda data=None: "pack"

            async def fake_full_reindex(**kwargs):
                state = kwargs["progress_state"]
                state.update(
                    processed=2,
                    total=2,
                    skipped=1,
                    reindexed=1,
                    errors=0,
                    changed_file_count=2,
                )
                return {
                    "processed": 2,
                    "total": 2,
                    "skipped": 1,
                    "reindexed": 1,
                    "errors": 0,
                    "changed_file_count": 2,
                }

            instance._ensure_flat_library_index = AsyncMock(side_effect=fake_full_reindex)

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
        self.assertEqual(finished["skipped"], 1)
        self.assertEqual(finished["reindexed"], 1)
        self.assertEqual(finished["errors"], 0)
        self.assertIn("跳过 1 张", finished["message"])
        instance._ensure_flat_library_index.assert_awaited_once()
        call_kwargs = instance._ensure_flat_library_index.await_args.kwargs
        self.assertTrue(call_kwargs["full_reindex"])
        self.assertEqual(call_kwargs["progress_state"], instance._reindex_states["pack"])

    async def test_reindex_task_failure_is_exposed_in_state(self):
        instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)

        async def fail_during_reindex(*_args, **_kwargs):
            raise RuntimeError("catalog exploded")

        instance._reindex_pack_catalog_with_progress = fail_during_reindex
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

    async def test_reindex_does_not_hold_pack_lock_during_model_work(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            pack_dir.mkdir(parents=True)
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance.catalog_index_service = CatalogIndexService(pack_dir.parent)
            started = asyncio.Event()
            release = asyncio.Event()
            state = {
                "pack_id": "pack",
                "status": "running",
                "processed": 0,
                "total": 1,
                "changed_file_count": 0,
                "message": "running",
            }

            async def fake_model_work(_pack_id, _state):
                started.set()
                await release.wait()
                return {"processed": 1, "total": 1, "errors": 0, "reindexed": 1, "skipped": 0}

            instance._reindex_pack_catalog_with_progress = fake_model_work
            try:
                with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent):
                    task = asyncio.create_task(instance._run_reindex_task("pack", state))
                    await asyncio.wait_for(started.wait(), timeout=1)
                    mutation_ran = False

                    def dispose_marker():
                        nonlocal mutation_ran
                        mutation_ran = True

                    await asyncio.wait_for(
                        instance.catalog_index_service.run_locked_pack_mutation(
                            "pack", "dispose", dispose_marker
                        ),
                        timeout=0.2,
                    )
                    release.set()
                    await task
            finally:
                release.set()
                if "task" in locals() and not task.done():
                    await task

        self.assertTrue(mutation_ran)

    async def test_reindex_status_defaults_include_full_scan_counters(self):
        instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
        instance._capture_pack_id = lambda data=None: "pack"
        instance._reindex_states = {}

        class Request:
            args = {"pack_id": "pack"}

        with (
            patch.object(capture_index_api, "request", Request()),
            patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
        ):
            result = await instance._api_capture_reindex_status()

        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["reindexed"], 0)
        self.assertEqual(result["errors"], 0)

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

    async def test_manual_pending_index_rejects_an_active_full_reindex(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            store.save_image(b"pending", "happy", ".png")
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance.store = store
            instance._capture_pack_id = lambda data=None: "pack"
            instance._library_task = None
            instance._library_index_state = {}
            never_finished = asyncio.create_task(asyncio.Event().wait())
            instance._reindex_tasks = {"pack": never_finished}

            class Request:
                async def get_json(self):
                    return {"pack_id": "pack"}

            try:
                with (
                    patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent),
                    patch.object(capture_index_api, "request", Request()),
                    patch.object(capture_index_api, "jsonify", side_effect=lambda payload: payload),
                ):
                    response = await instance._api_capture_index()
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
            instance._ensure_flat_library_index = AsyncMock(
                return_value={
                    "processed": 0,
                    "total": 0,
                    "changed_file_count": 0,
                    "skipped": 0,
                    "reindexed": 0,
                    "errors": 0,
                }
            )

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
