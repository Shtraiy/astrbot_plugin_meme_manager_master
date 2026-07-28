"""AstrBot Meme Manager: pack-aware WebUI, semantic selection and auto capture."""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, register

from .capture import CaptureMixin
from .manager_base import MemeSender


@register(
    "meme_manager_master",
    "Shtraiy",
    "表情包管理大师：WebUI 管理、智能选图与群聊表情包自动收集。",
    "2.0.0",
)
class MemeManager(CaptureMixin, MemeSender):
    """独立于原版 meme_manager 的管理运行时，并整合自动收集流程。"""

    def __init__(self, context: Context, config: dict | None = None):
        # CaptureMixin owns the collection queues and health state.  The
        # reference manager then initializes packs, WebUI routes and prompts.
        CaptureMixin.__init__(self, context, config)
        MemeSender.__init__(self, context, config)

    @filter.event_message_type(EventMessageType.ALL)
    async def capture_images(self, event: AstrMessageEvent, *args, **kwargs):
        await CaptureMixin.on_message(self, event, *args, **kwargs)

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_upload_image(self, event: AstrMessageEvent):
        async for result in MemeSender.handle_upload_image(self, event):
            yield result

    @filter.on_llm_request(priority=99999)
    async def inject_meme_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        await MemeSender.inject_meme_prompt(self, event, req)
        await CaptureMixin.on_llm_request(self, event, req)

    @filter.on_llm_response(priority=99999)
    async def resp(self, event: AstrMessageEvent, response: LLMResponse):
        return await MemeSender.resp(self, event, response)

    @filter.on_decorating_result(priority=100000)
    async def on_decorating_result(self, event: AstrMessageEvent):
        # The reference sender is the sole outgoing image authority.  This
        # prevents the legacy random sender from racing semantic exact-ID
        # selection and producing duplicate images.
        return await MemeSender.on_decorating_result(self, event)

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        return await MemeSender.after_message_sent(self, event)

    @filter.command("偷取", priority=100000)
    async def steal_command(self, event: AstrMessageEvent):
        async for result in CaptureMixin.steal_command(self, event):
            yield result

    @filter.command("发送表情包", priority=100000)
    @filter.command("发刚才的表情包", priority=100000)
    async def send_last_stolen_image(self, event: AstrMessageEvent):
        async for result in CaptureMixin.send_last_stolen_image(self, event):
            yield result

    @filter.command("表情偷取状态")
    async def capture_status(self, event: AstrMessageEvent):
        async for result in CaptureMixin.status(self, event):
            yield result

    @filter.on_using_llm_tool()
    async def on_using_llm_tool(self, event: AstrMessageEvent, tool, tool_args=None):
        return await CaptureMixin.on_using_llm_tool(self, event, tool, tool_args)

    async def terminate(self):
        manager_error = None
        try:
            await MemeSender.terminate(self)
        except Exception as exc:  # preserve capture task cleanup on shutdown
            manager_error = exc
            logger.warning("[meme_manager_master] manager shutdown cleanup failed: %s", exc)
        await CaptureMixin.terminate(self)
        if manager_error:
            raise manager_error
