import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.fakes import install_package_alias, install_runtime_stubs
from storage import MemeStore


install_runtime_stubs()
install_package_alias()

from meme_manager_master.capture_pipeline import CapturePipeline  # noqa: E402


class _Config:
    fallback_category = "happy"
    perceptual_dedupe_enabled = False


class CapturePipelineTests(unittest.TestCase):
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
                        "description": vision.get("description", ""),
                        "emotion": vision.get("emotion", ""),
                        "text": vision.get("text", ""),
                        "tags": [category, *(vision.get("tags") or [])],
                    },
                    bind_saved_result=lambda _event, _path: None,
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
        self.assertEqual(tags, ["开心", "疑惑", "嘲讽"])
        self.assertEqual(description, "新的识别描述")
        self.assertEqual(image_count, 1)
        self.assertEqual(events[0]["status"], "duplicate")


if __name__ == "__main__":
    unittest.main()
