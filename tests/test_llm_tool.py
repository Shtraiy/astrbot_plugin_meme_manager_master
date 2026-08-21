import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from tests.fakes import (
    FakeContext,
    FakeEvent,
    install_package_alias,
    install_runtime_stubs,
)


install_runtime_stubs()
install_package_alias()

from astrbot.api.message_components import Image as CompImage  # noqa: E402
from meme_manager_master.capture import CaptureMixin  # noqa: E402
from meme_manager_master.collector import event_identity  # noqa: E402
from meme_manager_master.llm_tools import (  # noqa: E402
    SendMemeTool,
    register_send_meme_tool,
)


class SendMemeToolContractTests(unittest.TestCase):
    def test_tool_metadata_is_decision_complete(self):
        tool = SendMemeTool(plugin=object())
        self.assertEqual(tool.name, "send_meme")
        self.assertIn("表情包", tool.description)
        self.assertEqual(tool.parameters["type"], "object")
        self.assertIn("reason", tool.parameters["properties"])
        self.assertIn("category", tool.parameters["properties"])
        self.assertEqual(tool.parameters["required"], [])

    def test_call_extracts_event_from_wrapper_and_passes_kwargs(self):
        class FakePlugin:
            async def send_meme_via_tool(self, event, *, reason="", category=""):
                self.received = (event, reason, category)
                return "已发送表情包:happy · meme.png"

        plugin = FakePlugin()
        tool = SendMemeTool(plugin=plugin)
        event = FakeEvent(message_text="哈哈")
        from astrbot.core.agent.run_context import ContextWrapper

        wrapper = ContextWrapper(event=event)
        result = asyncio.run(
            tool.call(wrapper, reason="开心", category="happy")
        )
        self.assertEqual(result, "已发送表情包:happy · meme.png")
        self.assertEqual(plugin.received[0], event)
        self.assertEqual(plugin.received[1], "开心")
        self.assertEqual(plugin.received[2], "happy")

    def test_call_falls_back_to_nested_agent_context_event(self):
        class FakePlugin:
            async def send_meme_via_tool(self, event, *, reason="", category=""):
                self.received = event
                return "ok"

        plugin = FakePlugin()
        tool = SendMemeTool(plugin=plugin)
        event = FakeEvent(message_text="哈哈")
        from astrbot.core.agent.run_context import ContextWrapper
        from astrbot.core.astr_agent_context import AstrAgentContext

        agent_context = AstrAgentContext(event=event)
        wrapper = ContextWrapper(context=agent_context)
        result = asyncio.run(tool.call(wrapper))
        self.assertEqual(result, "ok")
        self.assertEqual(plugin.received, event)

    def test_call_returns_error_text_when_plugin_raises(self):
        class FakePlugin:
            async def send_meme_via_tool(self, event, *, reason="", category=""):
                raise RuntimeError("boom")

        tool = SendMemeTool(plugin=FakePlugin())
        from astrbot.core.agent.run_context import ContextWrapper

        result = asyncio.run(
            tool.call(ContextWrapper(event=FakeEvent(message_text="哈哈")))
        )
        self.assertEqual(result, "发送表情包失败,请稍后再试。")

    def test_register_uses_context_add_llm_tools(self):
        context = FakeContext()
        self.assertTrue(register_send_meme_tool(object(), context))
        self.assertEqual(
            [tool.name for tool in context.registered_llm_tools],
            ["send_meme"],
        )

    def test_register_falls_back_to_provider_func_list(self):
        context = FakeContext()
        context.add_llm_tools = None
        self.assertTrue(register_send_meme_tool(object(), context))
        self.assertEqual(
            [tool.name for tool in context.provider_manager.llm_tools.func_list],
            ["send_meme"],
        )


class SendMemeViaToolBehaviorTests(unittest.TestCase):
    def _make_mixin(self, config=None, context=None) -> CaptureMixin:
        async def create():
            active_context = context or FakeContext()
            mixin = CaptureMixin(active_context, config or {})
            mixin.context = active_context
            return mixin

        return asyncio.run(create())

    def test_disabled_tool_returns_not_available_without_selecting(self):
        mixin = self._make_mixin({"llm_tool_enabled": False})
        mixin._manager_ready = AsyncMock(return_value=True)
        choose = AsyncMock(return_value=None)
        mixin.meme_selection.choose = choose
        context = mixin.context
        context.send_message = AsyncMock()

        result = asyncio.run(
            mixin.send_meme_via_tool(FakeEvent(message_text="哈哈"), reason="开心")
        )

        self.assertEqual(result, "表情包发送工具未启用或当前会话不在可用范围。")
        choose.assert_not_awaited()
        context.send_message.assert_not_awaited()

    def test_whitelist_blocked_tool_returns_not_available(self):
        mixin = self._make_mixin({"group_whitelist": ["10001"]})
        mixin._manager_ready = AsyncMock(return_value=True)
        choose = AsyncMock(return_value=None)
        mixin.meme_selection.choose = choose
        context = mixin.context
        context.send_message = AsyncMock()

        result = asyncio.run(
            mixin.send_meme_via_tool(FakeEvent(message_text="哈哈"), reason="开心")
        )

        self.assertEqual(result, "表情包发送工具未启用或当前会话不在可用范围。")
        choose.assert_not_awaited()
        context.send_message.assert_not_awaited()

    def test_success_sends_file_image_and_records_marker(self):
        class RecordingContext(FakeContext):
            async def send_message(self, umo, chain):
                self.sent = (umo, chain)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meme.png"
            path.write_bytes(b"placeholder")
            event = FakeEvent(message_text="哈哈")
            context = RecordingContext()
            mixin = self._make_mixin(
                {"auto_send_cooldown": 0}, context=context
            )
            mixin._manager_ready = AsyncMock(return_value=True)
            choose = AsyncMock(return_value=path)
            mixin.meme_selection.choose = choose
            mixin._image_details = lambda _path: {
                "category": "happy",
                "filename": _path.name,
                "description": "",
                "emotion": "happy",
                "tags": [],
            }
            mixin._record_image_send = AsyncMock()

            result = asyncio.run(
                mixin.send_meme_via_tool(event, reason="开心", category="happy")
            )

            self.assertEqual(result, "已发送表情包:happy · meme.png")
            choose.assert_awaited_once()
            self.assertEqual(choose.await_args.kwargs["force_send"], True)
            self.assertEqual(choose.await_args.kwargs["preferred_categories"], ["happy"])
            sent_umo, chain = context.sent
            self.assertEqual(sent_umo, event.unified_msg_origin)
            self.assertEqual(chain.message[0].path, str(path))
            self.assertTrue(event.get_extra("meme_manager_master_llm_tool_sent"))
            self.assertIn(event.unified_msg_origin, mixin._last_auto_send)

    def test_no_selected_image_returns_no_meme_text(self):
        mixin = self._make_mixin({"auto_send_cooldown": 0})
        mixin._manager_ready = AsyncMock(return_value=True)
        choose = AsyncMock(return_value=None)
        mixin.meme_selection.choose = choose
        context = mixin.context
        context.send_message = AsyncMock()

        result = asyncio.run(
            mixin.send_meme_via_tool(FakeEvent(message_text="哈哈"), reason="开心")
        )

        self.assertEqual(result, "本地表情包库暂无可发送的表情包。")
        context.send_message.assert_not_awaited()

    def test_cooldown_claim_failure_does_not_send(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meme.png"
            path.write_bytes(b"placeholder")
            event = FakeEvent(message_text="哈哈")
            mixin = self._make_mixin({"auto_send_cooldown": 0})
            mixin._manager_ready = AsyncMock(return_value=True)
            choose = AsyncMock(return_value=path)
            mixin.meme_selection.choose = choose
            mixin._record_image_send = AsyncMock()
            context = mixin.context
            context.send_message = AsyncMock()
            mixin._auto_send_claims[event_identity(event)] = 1.0

            result = asyncio.run(
                mixin.send_meme_via_tool(event, reason="开心")
            )

            self.assertEqual(result, "刚刚已发送过表情包,暂不重复发送。")
            context.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
