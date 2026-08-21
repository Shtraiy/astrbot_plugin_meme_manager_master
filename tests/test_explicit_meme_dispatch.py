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
from meme_manager_master.storage import MemeStore  # noqa: E402


ROOT = Path(__file__).parents[1]


class ExplicitMemeDispatchBehaviorTests(unittest.TestCase):
    def _make_mixin(self, config=None, context=None) -> CaptureMixin:
        async def create():
            active_context = context or FakeContext()
            mixin = CaptureMixin(active_context, config or {})
            mixin.context = active_context
            return mixin

        return asyncio.run(create())

    def test_auto_send_records_only_after_context_send_succeeds(self):
        class RecordingContext(FakeContext):
            async def send_message(self, umo, chain):
                self.sent = (umo, chain)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            saved = store.save_image(b"image", ["happy"], ".png", None)
            context = RecordingContext()
            mixin = self._make_mixin(context=context)
            mixin.store = store
            event = FakeEvent()
            event.set_extra("meme_manager_master_auto_send_path", str(saved.path))
            event.set_extra("meme_manager_master_auto_send_details", {})

            asyncio.run(mixin.after_message_sent(event))

            item = store.load_catalog()["items"][0]
            self.assertEqual(item["send_count"], 1)
            self.assertTrue(hasattr(context, "sent"))

    def test_auto_send_failure_does_not_record_weight(self):
        class FailingContext(FakeContext):
            async def send_message(self, umo, chain):
                raise RuntimeError("send failed")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemeStore(Path(temp_dir) / "pack")
            saved = store.save_image(b"image", ["happy"], ".png", None)
            mixin = self._make_mixin(context=FailingContext())
            mixin.store = store
            event = FakeEvent()
            event.set_extra("meme_manager_master_auto_send_path", str(saved.path))
            event.set_extra("meme_manager_master_auto_send_details", {})

            asyncio.run(mixin.after_message_sent(event))

            item = store.load_catalog()["items"][0]
            self.assertEqual(item["send_count"], 0)
            self.assertEqual(item["last_sent_at"], 0)

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
            choose = AsyncMock(return_value=path)
            mixin._choose_outgoing_meme_from_index = choose
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
            self.assertFalse(choose.await_args.kwargs["force_send"])
            self.assertEqual(choose.await_args.kwargs["preferred_categories"], ["sad"])

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

    def test_explicit_request_does_not_leak_into_a_later_generation_event(self):
        first_event = FakeEvent(
            message_text="再发一个可爱猫猫标签",
            umo="group-shared",
            message_id="meme-request",
        )
        generation_event = FakeEvent(
            message_text="生成自拍，写实摄影风格，高中校园走廊",
            umo="group-shared",
            message_id="image-generation",
        )
        generation_event.set_result(FakeResult([CompPlain("图片已生成。")]))
        mixin = self._make_mixin(
            {"auto_send_probability": 100, "auto_send_cooldown": 0}
        )
        mixin._manager_ready = AsyncMock(return_value=True)
        choose = AsyncMock(return_value=None)
        mixin._choose_outgoing_meme_from_index = choose

        asyncio.run(mixin.on_message(first_event))
        asyncio.run(mixin.on_decorating_result(generation_event))

        choose.assert_awaited_once()
        self.assertFalse(choose.await_args.kwargs["force_send"])
        self.assertFalse(generation_event.stopped)

    def test_external_image_reply_skips_local_meme_selection(self):
        event = FakeEvent(message_text="生成自拍，写实摄影风格")
        event.set_result(
            FakeResult(
                [
                    CompPlain("已生成图片。"),
                    CompImage.fromFileSystem("generated.png"),
                ]
            )
        )
        mixin = self._make_mixin(
            {"auto_send_probability": 100, "auto_send_cooldown": 0}
        )
        mixin._manager_ready = AsyncMock(return_value=True)
        choose = AsyncMock(return_value=None)
        mixin._choose_outgoing_meme_from_index = choose

        asyncio.run(mixin.on_decorating_result(event))

        choose.assert_not_awaited()
        self.assertFalse(event.stopped)

    def test_natural_language_meme_request_does_not_block_image_tool_without_guard(self):
        event = FakeEvent(message_text="再发一个可爱猫猫标签")
        mixin = self._make_mixin()

        asyncio.run(
            mixin.on_using_llm_tool(
                event,
                "astrbot_execute_python",
                None,
            )
        )

        self.assertFalse(event.stopped)

    def test_llm_request_does_not_stop_natural_language_event(self):
        event = FakeEvent(message_text="再发一个可爱猫猫标签")
        mixin = self._make_mixin()

        asyncio.run(mixin.on_llm_request(event, object()))

        self.assertFalse(event.stopped)

    def test_unverified_send_claim_is_rewritten_without_receipt(self):
        event = FakeEvent()
        chain = [CompPlain("表情包已经发给你啦～"), CompPlain("其他正文")]
        mixin = self._make_mixin()
        mixin._rewrite_unverified_meme_claim(event, chain)
        self.assertEqual(chain[0].text, "")
        self.assertEqual(chain[1].text, "其他正文")

    def test_unverified_send_claim_does_not_replace_the_rest_of_the_reply(self):
        event = FakeEvent()
        chain = [CompPlain("这个表情有点像你，表情包已经发给你啦～")]
        mixin = self._make_mixin()

        mixin._rewrite_unverified_meme_claim(event, chain)

        self.assertEqual(chain[0].text, "这个表情有点像你")

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

    def test_send_meme_tool_use_is_not_blocked(self):
        event = FakeEvent(message_text="哈哈")
        mixin = self._make_mixin()

        asyncio.run(
            mixin.on_using_llm_tool(
                event,
                {"name": "send_meme"},
                {"reason": "开心"},
            )
        )

        self.assertFalse(event.stopped)

    def test_llm_tool_sent_marker_skips_auto_selection(self):
        event = FakeEvent(message_text="哈哈")
        event.set_result(FakeResult([CompPlain("笑死我了")]))
        event.set_extra("meme_manager_master_llm_tool_sent", True)
        mixin = self._make_mixin(
            {"auto_send_probability": 100, "auto_send_cooldown": 0}
        )
        mixin._manager_ready = AsyncMock(return_value=True)
        choose = AsyncMock(return_value=None)
        mixin._choose_outgoing_meme_from_index = choose

        asyncio.run(mixin.on_decorating_result(event))

        choose.assert_not_awaited()

    def test_legacy_success_copy_is_absent(self):
        source = (ROOT / "capture.py").read_text(encoding="utf-8")
        self.assertNotIn("找到一个合适的表情包", source)
        self.assertNotIn("找到了一个合适的表情包", source)


if __name__ == "__main__":
    unittest.main()
