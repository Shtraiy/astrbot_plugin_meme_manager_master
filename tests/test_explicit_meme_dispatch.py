import asyncio
import tempfile
import time
import unittest
from unittest.mock import AsyncMock
from pathlib import Path

from tests.fakes import (
    FakeContext,
    FakeEvent,
    FakeResult,
    install_package_alias,
    install_runtime_stubs,
)


install_runtime_stubs()
install_package_alias()

from astrbot.api.message_components import Image as CompImage  # noqa: E402
from astrbot.api.message_components import Plain as CompPlain  # noqa: E402
from meme_manager_master.capture import CaptureMixin  # noqa: E402
from meme_manager_master.collector import event_identity  # noqa: E402


ROOT = Path(__file__).parents[1]


class ExplicitMemeDispatchBehaviorTests(unittest.TestCase):
    def _make_mixin(self, config=None) -> CaptureMixin:
        async def create():
            return CaptureMixin(FakeContext(), config or {})

        return asyncio.run(create())

    def test_explicit_success_chain_emits_only_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meme.png"
            path.write_bytes(b"placeholder")
            chain = CaptureMixin._explicit_success_chain(path)
            self.assertEqual(len(chain), 1)
            self.assertIsInstance(chain[0], CompImage)

    def test_auto_send_chain_preserves_agent_reply_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meme.png"
            path.write_bytes(b"placeholder")
            chain = CaptureMixin._explicit_success_chain(path, "这也太离谱了哈哈。")
            self.assertEqual(len(chain), 2)
            self.assertIsInstance(chain[0], CompPlain)
            self.assertEqual(chain[0].text, "这也太离谱了哈哈。")
            self.assertIsInstance(chain[1], CompImage)

    def test_marker_only_reply_embeds_selected_meme_in_current_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meme.png"
            path.write_bytes(b"placeholder")
            event = FakeEvent()
            event.set_result(FakeResult([CompPlain("&&sad&&")]))
            mixin = self._make_mixin(
                {"auto_send_probability": 100, "auto_send_cooldown": 0}
            )
            mixin._manager_ready = AsyncMock(return_value=True)
            mixin._choose_outgoing_meme_from_index = AsyncMock(return_value=path)
            mixin._image_details = lambda _path: {
                "category": "sad",
                "filename": path.name,
                "description": "",
                "emotion": "sad",
                "tags": [],
            }

            asyncio.run(mixin.on_decorating_result(event))

            self.assertEqual(len(event.get_result().chain), 1)
            self.assertIsInstance(event.get_result().chain[0], CompImage)
            self.assertIsNone(event.get_extra("meme_manager_master_auto_send_path"))
            self.assertEqual(
                event.get_extra("meme_manager_master_send_mark_path"),
                str(path),
            )

    def test_text_reply_without_filter_hook_embeds_selected_meme_in_current_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meme.png"
            path.write_bytes(b"placeholder")
            event = FakeEvent()
            event.set_result(FakeResult([CompPlain("我也觉得很遗憾。 &&sad&&")]))
            mixin = self._make_mixin(
                {"auto_send_probability": 100, "auto_send_cooldown": 0}
            )
            mixin._manager_ready = AsyncMock(return_value=True)
            mixin._choose_outgoing_meme_from_index = AsyncMock(return_value=path)
            mixin._image_details = lambda _path: {
                "category": "sad",
                "filename": path.name,
                "description": "",
                "emotion": "sad",
                "tags": [],
            }

            asyncio.run(mixin.on_decorating_result(event))

            self.assertEqual(len(event.get_result().chain), 2)
            self.assertEqual(event.get_result().chain[0].text, "我也觉得很遗憾。")
            self.assertIsInstance(event.get_result().chain[1], CompImage)
            self.assertIsNone(event.get_extra("meme_manager_master_auto_send_path"))

    def test_text_reply_with_filter_hook_defers_selected_meme_until_after_send(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meme.png"
            path.write_bytes(b"placeholder")
            event = FakeEvent()
            event.set_result(FakeResult([CompPlain("我也觉得很遗憾。 &&sad&&")]))
            async def add_filter_lock():
                event.set_extra("astrbot_plugin_filter_reply_lock", asyncio.Lock())

            asyncio.run(add_filter_lock())
            mixin = self._make_mixin(
                {"auto_send_probability": 100, "auto_send_cooldown": 0}
            )
            mixin._manager_ready = AsyncMock(return_value=True)
            mixin._choose_outgoing_meme_from_index = AsyncMock(return_value=path)
            mixin._image_details = lambda _path: {
                "category": "sad",
                "filename": path.name,
                "description": "",
                "emotion": "sad",
                "tags": [],
            }

            asyncio.run(mixin.on_decorating_result(event))

            self.assertEqual(len(event.get_result().chain), 1)
            self.assertEqual(event.get_result().chain[0].text, "我也觉得很遗憾。")
            self.assertEqual(
                event.get_extra("meme_manager_master_auto_send_path"),
                str(path),
            )

    def test_unverified_send_claim_is_rewritten_without_receipt(self):
        event = FakeEvent()
        chain = [CompPlain("表情包已经发给你啦～"), CompPlain("其他正文")]
        mixin = self._make_mixin()
        mixin._rewrite_unverified_meme_claim(event, chain)
        self.assertEqual(chain[0].text, "我还没有成功发送表情包。")
        self.assertEqual(chain[1].text, "其他正文")

    def test_send_claim_is_preserved_when_receipt_exists(self):
        event = FakeEvent(message_id="msg-with-receipt")
        mixin = self._make_mixin()
        mixin._meme_send_receipts[event_identity(event)] = (
            time.monotonic(),
            Path("meme.png"),
            {"category": "happy"},
        )
        original = "表情包已经发给你啦～"
        chain = [CompPlain(original)]
        mixin._rewrite_unverified_meme_claim(event, chain)
        self.assertEqual(chain[0].text, original)

    def test_terminate_cancels_capture_tasks(self):
        async def scenario():
            mixin = CaptureMixin(FakeContext(), {})

            async def never():
                await asyncio.sleep(3600)

            health = asyncio.create_task(never())
            library = asyncio.create_task(never())
            other = asyncio.create_task(never())
            mixin._health_task = health
            mixin._library_task = library
            mixin._tasks = {other}
            await mixin.terminate()
            return health.cancelled(), library.cancelled(), other.cancelled()

        cancelled = asyncio.run(scenario())
        self.assertTrue(all(cancelled))

    def test_legacy_success_copy_is_absent(self):
        source = (ROOT / "capture.py").read_text(encoding="utf-8")
        self.assertNotIn("找到一个合适的表情包", source)
        self.assertNotIn("找到了一个合适的表情包", source)


if __name__ == "__main__":
    unittest.main()
