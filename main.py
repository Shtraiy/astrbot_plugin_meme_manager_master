"""AstrBot Meme Manager: pack-aware WebUI, semantic selection and auto capture."""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, register

from .capture import CaptureMixin
from .manager_base import MemeSender
from .storage import MemeStore


@register(
    "meme_manager_master",
    "Shtraiy",
    "表情包管理大师：WebUI 管理、智能选图与群聊表情包自动收集。",
    "2.4.1",
)
class MemeManager(CaptureMixin, MemeSender):
    """独立于原版 meme_manager 的管理运行时，并整合自动收集流程。"""

    def __init__(self, context: Context, config: dict | None = None):
        # CaptureMixin owns the collection queues and health state.  The
        # reference manager then initializes packs, WebUI routes and prompts.
        CaptureMixin.__init__(self, context, config)
        MemeSender.__init__(self, context, config)
        try:
            repaired = 0
            packs_root = self.store.root.parent
            if packs_root.is_dir():
                for pack_dir in packs_root.iterdir():
                    if pack_dir.is_dir():
                        repaired += MemeStore(pack_dir).reconcile_catalogs()
            if repaired:
                logger.info(
                    "[meme_manager_master] 已补齐 %d 个分类的 index.json 与 README.md",
                    repaired,
                )
        except Exception as exc:
            logger.warning("[meme_manager_master] 分类索引初始化失败: %s", exc)

    @filter.event_message_type(EventMessageType.ALL)
    async def capture_images(self, event: AstrMessageEvent, *args, **kwargs):
        await CaptureMixin.on_message(self, event, *args, **kwargs)

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_upload_image(self, event: AstrMessageEvent):
        async for result in MemeSender.handle_upload_image(self, event):
            yield result

    @filter.on_llm_request(priority=99999)
    async def prepare_meme_request(self, event: AstrMessageEvent, req: ProviderRequest):
        await CaptureMixin.on_llm_request(self, event, req)

    @filter.on_decorating_result(priority=100000)
    async def on_decorating_result(self, event: AstrMessageEvent):
        return await CaptureMixin.on_decorating_result(self, event)

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        # Keep the reference manager's pending-image compatibility path, then
        # send CaptureMixin's selected automatic image after the reply.
        await MemeSender.after_message_sent(self, event)
        await CaptureMixin.after_message_sent(self, event)

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
