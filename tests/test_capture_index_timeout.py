import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

from meme_manager_master import capture as capture_module
from meme_manager_master.capture import CaptureMixin
from meme_manager_master.runtime_config import PluginConfig
from meme_manager_master.storage import MemeStore


class LibraryIndexTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_batch_results_retry_only_missing_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            first_path = store.save_image(b"first", "happy", ".png").path
            second_path = store.save_image(b"second", "happy", ".png").path
            instance = self._make_instance(store, batch_size=2)
            metadata = {
                "description": "测试图片",
                "emotion": "开心",
                "text": "",
                "tags": ["开心"],
                "indexed": True,
            }
            instance._describe_library_batch = AsyncMock(
                return_value={first_path: metadata}
            )
            instance._describe_library_single = AsyncMock(
                return_value={second_path: metadata}
            )

            await instance._ensure_flat_library_index()

        instance._describe_library_single.assert_awaited_once_with(
            None, second_path, "固定标签", "provider"
        )
        self.assertEqual(instance._library_index_state["status"], "completed")
        self.assertEqual(instance._library_index_state["errors"], 0)

    async def test_single_timeout_retries_once_before_failing(self):
        instance = CaptureMixin.__new__(CaptureMixin)
        image_path = Path("meme_retry.png")
        instance._generate = AsyncMock(
            side_effect=[
                asyncio.TimeoutError(),
                '{"description":"测试图片","emotion":"开心","text":"","tags":["开心"]}',
            ]
        )

        with patch.object(capture_module, "LIBRARY_INDEX_LLM_TIMEOUT", 0.01, create=True), patch.object(
            capture_module, "LIBRARY_INDEX_RETRY_DELAY", 0, create=True
        ):
            result = await instance._describe_library_single(
                None, image_path, "固定标签", "provider"
            )

        self.assertIn(image_path, result)
        self.assertEqual(instance._generate.await_count, 2)

    async def test_batch_model_call_has_a_bounded_timeout(self):
        instance = CaptureMixin.__new__(CaptureMixin)
        calls = 0

        async def returns_too_late(*args, **kwargs):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.03)
            return '{"items": []}'

        instance._generate = returns_too_late
        image_path = Path("meme_timeout.png")

        with patch.object(capture_module, "LIBRARY_INDEX_LLM_TIMEOUT", 0.01, create=True):
            with self.assertRaises(asyncio.TimeoutError):
                await instance._describe_library_batch(
                    None, [image_path], "固定标签", "provider"
                )
        self.assertEqual(calls, 1)

    async def test_batch_invalid_json_retries_once_and_accepts_valid_response(self):
        instance = CaptureMixin.__new__(CaptureMixin)
        image_paths = [Path("first.png"), Path("second.png")]
        instance._generate = AsyncMock(
            side_effect=[
                '<think>{"draft":{"invalid":true}}</think>\nnot-json',
                (
                    '```json\n'
                    '{"items":['
                    '{"id":"image_0","description":"第一张","emotion":"开心",'
                    '"text":"","tags":["开心"]},'
                    '{"id":"image_1","description":"第二张","emotion":"疑惑",'
                    '"text":"","tags":["疑惑"]}'
                    ']}\n'
                    '识别完成。'
                ),
            ]
        )

        with patch.object(capture_module, "LIBRARY_INDEX_LLM_TIMEOUT", 0.01, create=True):
            result = await instance._describe_library_batch(
                None, image_paths, "固定标签", "provider"
            )

        self.assertEqual(set(result), set(image_paths))
        self.assertEqual(instance._generate.await_count, 2)

    async def test_batch_retry_exhaustion_falls_back_to_single_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            image_path = store.save_image(b"image", "happy", ".png").path
            instance = self._make_instance(store, batch_size=1)
            instance._generate = AsyncMock(
                side_effect=[
                    "not-json",
                    "still-not-json",
                    '{"description":"测试图片","emotion":"开心","text":"","tags":["开心"]}',
                ]
            )

            await instance._ensure_flat_library_index()

        self.assertEqual(instance._library_index_state["status"], "completed")
        self.assertEqual(instance._generate.await_count, 3)

    @staticmethod
    def _make_instance(store, *, batch_size=2):
        instance = CaptureMixin.__new__(CaptureMixin)
        instance.store = store
        instance.runtime_config = PluginConfig.from_mapping(
            {
                "library_index_provider_id": "provider",
                "library_index_batch_size": batch_size,
            }
        )
        instance._library_lock = asyncio.Lock()
        instance._save_lock = asyncio.Lock()
        instance._library_index_state = {
            "status": "idle",
            "processed": 0,
            "total": 0,
            "classified": 0,
            "errors": 0,
            "message": "尚未开始目录索引",
        }
        instance._library_retry_key = None
        instance._library_retry_at = 0.0
        instance._library_completed_key = None
        return instance

    async def test_invalid_json_batch_falls_back_to_single_image_calls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            image_path = store.save_image(b"image", "happy", ".png").path
            instance = self._make_instance(store, batch_size=1)
            instance._describe_library_batch = AsyncMock(
                side_effect=ValueError("model response contains invalid JSON")
            )
            instance._describe_library_single = AsyncMock(
                return_value={
                    image_path: {
                        "description": "测试图片",
                        "emotion": "开心",
                        "text": "",
                        "tags": ["开心"],
                        "indexed": True,
                    }
                }
            )

            await instance._ensure_flat_library_index()

        self.assertEqual(instance._library_index_state["status"], "completed")
        instance._describe_library_single.assert_awaited_once()

    async def test_all_single_image_timeouts_end_with_retryable_error_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            store.save_image(b"image", "happy", ".png")
            instance = self._make_instance(store, batch_size=1)
            instance._describe_library_batch = AsyncMock(
                side_effect=asyncio.TimeoutError()
            )
            instance._describe_library_single = AsyncMock(
                side_effect=asyncio.TimeoutError()
            )

            await instance._ensure_flat_library_index()

        self.assertEqual(
            instance._library_index_state["status"], "completed_with_errors"
        )
        self.assertNotEqual(instance._library_index_state["status"], "running")
        self.assertGreater(instance._library_index_state["errors"], 0)

    async def test_unexpected_background_task_exception_is_exposed_as_error(self):
        instance = CaptureMixin.__new__(CaptureMixin)
        instance._library_index_state = {"status": "running", "message": "running"}

        async def fail():
            raise RuntimeError("provider exploded")

        task = asyncio.create_task(fail())
        with self.assertRaises(RuntimeError):
            await task
        instance._log_library_task_failure(task)

        self.assertEqual(instance._library_index_state["status"], "error")
        self.assertIn("provider exploded", instance._library_index_state["message"])


if __name__ == "__main__":
    unittest.main()
