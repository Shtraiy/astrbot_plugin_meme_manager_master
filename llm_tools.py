"""LLM tool bridge: let the agent send one local meme per call."""

from __future__ import annotations

from typing import Any

try:
    from pydantic import Field
    from pydantic.dataclasses import dataclass
except ImportError:  # offline test environments without pydantic
    from dataclasses import dataclass, field as Field

from astrbot.api import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


LLM_TOOL_SEND_FAILED_TEXT = "发送表情包失败,请稍后再试。"


@dataclass
class SendMemeTool(FunctionTool[AstrAgentContext]):
    """Send one local meme to the current session when the LLM calls it."""

    plugin: Any = None
    name: str = "send_meme"
    description: str = (
        "发送一张本地表情包到当前会话。当回复需要配一张表达情绪、吐槽或调侃的本地表情包时调用;"
        "工具会自动选图并发送,可选参数 reason 描述想表达的情绪或语境,category 指定期望分类。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "想表达的情绪、语气或语境,用于选择最贴切的表情包,可省略。",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "期望的表情包分类(如 开心/嘲讽/无语),可省略,"
                        "省略时由情景模型自动判断。"
                    ),
                },
            },
            "required": [],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs: Any
    ) -> ToolExecResult:
        event = self._extract_event(context)
        if event is None:
            return LLM_TOOL_SEND_FAILED_TEXT
        reason = str(kwargs.get("reason") or "").strip()
        category = str(kwargs.get("category") or "").strip()
        try:
            return await self.plugin.send_meme_via_tool(
                event,
                reason=reason,
                category=category,
            )
        except Exception as exc:
            logger.warning(
                "[meme_manager_master] send_meme 工具调用失败: %s",
                exc,
            )
            return LLM_TOOL_SEND_FAILED_TEXT

    @staticmethod
    def _extract_event(context: Any) -> Any:
        """Return the AstrMessageEvent from either wrapper layer, if present."""
        if context is None:
            return None
        event = getattr(context, "event", None)
        if event is not None:
            return event
        agent_context = getattr(context, "context", None)
        return getattr(agent_context, "event", None)


def register_send_meme_tool(plugin: Any, context: Any) -> bool:
    """Register send_meme, preferring the modern ``add_llm_tools`` API."""
    try:
        tool = SendMemeTool(plugin=plugin)
        add_tools = getattr(context, "add_llm_tools", None)
        if callable(add_tools):
            add_tools(tool)
            return True
        tool_mgr = getattr(
            getattr(context, "provider_manager", None),
            "llm_tools",
            None,
        )
        if tool_mgr is not None and hasattr(tool_mgr, "func_list"):
            tool_mgr.func_list.append(tool)
            return True
    except Exception as exc:
        logger.warning(
            "[meme_manager_master] send_meme 工具注册失败: %s",
            exc,
        )
    return False
