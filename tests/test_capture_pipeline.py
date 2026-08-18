import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.fakes import install_package_alias, install_runtime_stubs
from capture_blacklist import CaptureBlacklist
from storage import MemeStore


install_runtime_stubs()
install_package_alias()

from meme_manager_master.capture_pipeline import CapturePipeline  # noqa: E402
from collector import should_skip_meme_result


class _Config:
    fallback_category = "happy"
    perceptual_dedupe_enabled = False


class CapturePipelineTests(unittest.TestCase):
    def _pipeline(
        self,
        *,
        store,
        payload,
        blacklist,
        events,
        calls,
        vision=None,
        should_skip=None,
    ):
        async def loader(_source: str):
            calls["loader"] += 1
            return payload

        async def recognize(_event, _temp_path, _message_text):
            calls["recognize"] += 1
            return vision or {"description": "描述", "emotion": "开心", "text": "", "tags": []}

        async def classify(_event, _vision, _categories, _message_text, _message_outline):
            calls["classify"] += 1
            return {"category": "happy", "tags": []}

        return CapturePipeline(
            store=store,
            config=_Config(),
            semaphore=asyncio.Semaphore(1),
            save_lock=asyncio.Lock(),
            generate=None,
            activity_recorder=lambda _root, **data: events.append(data),
            loader=loader,
            recognize_single=recognize,
            classify_single=classify,
            should_skip=should_skip or (lambda _vision: False),
            catalog_entry_builder=lambda path, category, vision, scene: {
                "filename": path.name,
                "description": vision.get("description", ""),
                "emotion": vision.get("emotion", ""),
                "text": vision.get("text", ""),
                "tags": [category],
            },
            bind_saved_result=lambda _event, _path: None,
            capture_blacklist=blacklist,
        )

    def test_low_score_capture_is_not_saved_or_recorded(self):
        async def run():
            with tempfile.TemporaryDirectory() as temporary:
                store = MemeStore(Path(temporary) / "pack")
                payload = SimpleNamespace(content=b"low-score-image", extension=".png")
                events = []
                vision = {
                    "is_meme": True,
                    "confidence": 0.99,
                    "meme_score": 69,
                    "content_type": "reaction_meme",
                    "has_expression": True,
                }
                pipeline = self._pipeline(
                    store=store,
                    payload=payload,
                    blacklist=None,
                    events=events,
                    calls={"loader": 0, "recognize": 0, "classify": 0},
                    vision=vision,
                    should_skip=should_skip_meme_result,
                )
                statuses = await pipeline.process_batch(None, ["source"], "message", "outline")
                return statuses, events, store.image_paths()

        statuses, events, images = asyncio.run(run())
        self.assertEqual(statuses, ["not_meme"])
        self.assertEqual(events, [])
        self.assertEqual(images, [])

    def test_blacklisted_payload_is_rejected_before_temp_file_and_models(self):
        async def run():
            with tempfile.TemporaryDirectory() as temporary:
                store = MemeStore(Path(temporary) / "pack")
                payload = SimpleNamespace(content=b"blocked-image", extension=".png")
                digest = hashlib.sha256(payload.content).hexdigest()
                events = []
                calls = {"loader": 0, "recognize": 0, "classify": 0}

                class Blacklist:
                    def contains(self, value):
                        return value == digest

                    def run_if_allowed(self, _digest, operation):
                        return True, operation()

                pipeline = self._pipeline(
                    store=store,
                    payload=payload,
                    blacklist=Blacklist(),
                    events=events,
                    calls=calls,
                )
                statuses = await pipeline.process_batch(None, ["source"], "message", "outline")

                return statuses, calls, events, store.image_paths(), list(store.temp_dir.glob("*"))

        statuses, calls, events, images, temporary_files = asyncio.run(run())
        self.assertEqual(statuses, ["blacklisted"])
        self.assertEqual(calls, {"loader": 1, "recognize": 0, "classify": 0})
        self.assertEqual(events, [])
        self.assertEqual(images, [])
        self.assertEqual(temporary_files, [])

    def test_blacklist_second_check_prevents_save_after_recognition(self):
        async def run():
            with tempfile.TemporaryDirectory() as temporary:
                store = MemeStore(Path(temporary) / "pack")
                payload = SimpleNamespace(content=b"racing-image", extension=".png")
                events = []
                calls = {"loader": 0, "recognize": 0, "classify": 0}

                class Blacklist:
                    def contains(self, _digest):
                        return False

                    def run_if_allowed(self, _digest, _operation):
                        return False, None

                pipeline = self._pipeline(
                    store=store,
                    payload=payload,
                    blacklist=Blacklist(),
                    events=events,
                    calls=calls,
                )
                statuses = await pipeline.process_batch(None, ["source"], "message", "outline")
                return statuses, calls, events, store.image_paths()

        statuses, calls, events, images = asyncio.run(run())
        self.assertEqual(statuses, ["blacklisted"])
        self.assertEqual(calls, {"loader": 1, "recognize": 1, "classify": 1})
        self.assertEqual(events, [])
        self.assertEqual(images, [])

    def test_duplicate_capture_merges_current_classification_tags(self):
        async def run() -> tuple[list[str], list[str], str, int, list[dict]]:
            with tempfile.TemporaryDirectory() as temp_dir:
                store = MemeStore(Path(temp_dir) / "pack")
                existing = store.save_image(
                    b"already-stored",
                    ["开心"],
                    ".png",
                    None,
                )
                events: list[dict] = []
                payload = SimpleNamespace(
                    content=b"already-stored",
                    extension=".png",
                )

                async def loader(_source: str):
                    return payload

                async def recognize(_event, _temp_path, _message_text):
                    return {
                        "description": "新的识别描述",
                        "emotion": "嘲讽",
                        "text": "",
                        "tags": ["嘲讽"],
                    }

                async def classify(
                    _event,
                    _vision,
                    _categories,
                    _message_text,
                    _message_outline,
                ):
                    return {"category": "happy", "tags": []}

                pipeline = CapturePipeline(
                    store=store,
                    config=_Config(),
                    semaphore=asyncio.Semaphore(1),
                    save_lock=asyncio.Lock(),
                    generate=None,
                    activity_recorder=lambda _root, **data: events.append(data),
                    loader=loader,
                    recognize_single=recognize,
                    classify_single=classify,
                    should_skip=lambda _vision: False,
                    catalog_entry_builder=lambda path, category, vision, scene: {
                        "filename": path.name,
                        "primary_category": category,
                        "description": vision.get("description", ""),
                        "emotion": vision.get("emotion", ""),
                        "text": vision.get("text", ""),
                        "tags": [category, *(vision.get("tags") or [])],
                    },
                    bind_saved_result=lambda _event, _path: None,
                    capture_blacklist=None,
                )

                statuses = await pipeline.process_batch(
                    None,
                    ["source"],
                    "message",
                    "outline",
                )
                self.assertEqual(existing.path, store.image_paths()[0])
                return (
                    statuses,
                    store.load_catalog()["items"][0]["tags"],
                    store.load_catalog()["items"][0]["description"],
                    len(store.image_paths()),
                    events,
                )

        statuses, tags, description, image_count, events = asyncio.run(run())

        self.assertEqual(statuses, ["duplicate"])
        self.assertEqual(tags, ["开心", "嘲讽"])
        self.assertEqual(description, "新的识别描述")
        self.assertEqual(image_count, 1)
        self.assertEqual(events[0]["status"], "duplicate")

    def test_duplicate_capture_is_auto_blacklisted_and_hidden_from_duplicate_queue(self):
        async def run():
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                store = MemeStore(root / "pack")
                existing = store.save_image(b"already-stored", ["开心"], ".png", None)
                blacklist = CaptureBlacklist(root / "plugin-data")
                events = []
                payload = SimpleNamespace(content=b"already-stored", extension=".png")
                pipeline = self._pipeline(
                    store=store,
                    payload=payload,
                    blacklist=blacklist,
                    events=events,
                    calls={"loader": 0, "recognize": 0, "classify": 0},
                )

                statuses = await pipeline.process_batch(None, ["source"], "message", "outline")

                return statuses, existing.path, events, blacklist.auto_entries()

        statuses, existing_path, events, auto_entries = asyncio.run(run())
        digest = hashlib.sha256(b"already-stored").hexdigest()
        self.assertEqual(statuses, ["duplicate"])
        self.assertIn(digest, auto_entries)
        self.assertEqual(events[0]["status"], "blacklisted")
        self.assertEqual(
            auto_entries,
            {digest: [{"pack_id": existing_path.parent.parent.name, "filename": existing_path.name}]},
        )

    def test_same_message_duplicate_is_auto_blacklisted_without_a_pending_event(self):
        async def run():
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                store = MemeStore(root / "pack")
                blacklist = CaptureBlacklist(root / "plugin-data")
                events = []
                pipeline = self._pipeline(
                    store=store,
                    payload=SimpleNamespace(content=b"same-message-image", extension=".png"),
                    blacklist=blacklist,
                    events=events,
                    calls={"loader": 0, "recognize": 0, "classify": 0},
                )

                statuses = await pipeline.process_batch(
                    None,
                    ["first-source", "second-source"],
                    "message",
                    "outline",
                )

                return statuses, events, blacklist.auto_entries(), store.image_paths()

        statuses, events, auto_entries, image_paths = asyncio.run(run())
        digest = hashlib.sha256(b"same-message-image").hexdigest()
        self.assertEqual(statuses, ["saved", "duplicate"])
        self.assertEqual(len(image_paths), 1)
        self.assertEqual(events[0]["status"], "pending")
        self.assertEqual(len(auto_entries), 1)
        self.assertIn(digest, auto_entries)


if __name__ == "__main__":
    unittest.main()
