"""Collect group images, classify them, and store them for meme_manager_master."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
from ipaddress import ip_address
import random
import re
import socket
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiohttp
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.star import Context

from .collector import (
    complete_batch_indices,
    contains_meme_send_claim,
    configured_provider_id,
    drop_empty_text_components,
    event_identity,
    explicit_meme_request,
    extract_meme_markers,
    extract_image_sources,
    group_id_from_event,
    is_meme_follow_up_request,
    is_safe_remote_image_url,
    normalize_category,
    parse_model_json,
    should_block_agent_tool_for_meme_request,
    should_skip_meme_result,
    strip_meme_markers,
    vision_failure_result,
    whitelist_allows,
)
from .capture_activity import (
    index_metadata_matches,
    mark_capture_events_indexed,
    record_capture_event,
)
from .health import MemeManagerHealth, check_meme_manager_master_health
from .indexing import catalog_needs_write, normalize_library_results
from .storage import MemeStore, detect_image_extension


VISION_SYSTEM_PROMPT = """
你是一个负责识别聊天表情包的视觉模型。请只输出 JSON，不要 Markdown，不要解释。
判断图片是否像聊天表情包：包含明显情绪、反应、吐槽、文字梗或用于表达态度的画面。
JSON 格式：
{"is_meme": true, "confidence": 0.0, "description": "简短中文描述", "emotion": "情绪", "text": "图片中的文字"}
""".strip()


VISION_BATCH_SYSTEM_PROMPT = """
你是群聊表情包批量视觉识别器。输入包含多张图片，请逐张输出结果，必须保留每张图片的 id。
判断图片是否像聊天表情包：包含明显情绪、反应、吐槽、文字梗或用于表达态度的画面。
只输出 JSON，不要 Markdown。
格式：{"items":[{"id":"image_0", "is_meme":true, "confidence":0.0, "description":"简短中文描述", "emotion":"情绪", "text":"图片文字"}]}
""".strip()


def _scene_system_prompt(categories: set[str]) -> str:
    category_text = ", ".join(sorted(categories))
    return f"""
你是群聊表情包分类器。只能从以下分类中选择一个：{category_text}
请结合图片识别结果和消息语境，选择最适合日常聊天使用的分类。
只输出 JSON，不要 Markdown，不要输出列表外的分类。
JSON 格式：{{"category": "分类名", "confidence": 0.0, "reason": "不超过30字的理由"}}
""".strip()


def _scene_batch_system_prompt(categories: set[str]) -> str:
    category_text = ", ".join(sorted(categories))
    return f"""
你是群聊表情包批量情景分类器。输入包含多张图片的识别结果和同一条消息语境。
请为每个图片 id 选择一个最合适的分类，只能从以下分类中选择：{category_text}
只输出 JSON，不要 Markdown。
格式：{{"items":[{{"id":"image_0", "category":"分类名", "confidence":0.0, "reason":"不超过30字"}}]}}
""".strip()


def _library_batch_system_prompt(category: str) -> str:
    return f"""
你是表情包素材库批量整理器。当前收到多张图片，它们都已经位于 meme_manager_master 的 {category} 分类目录。
目录名是权威分类，不要移动或重新分类图片。请为每张图片输出一条结果，并严格保留输入的 id。
只输出 JSON，不要 Markdown。
格式：{{"items":[{{"id":"image_0", "description":"不超过40字", "emotion":"主要情绪", "text":"图片文字，没有则为空", "tags":["关键词1"]}}]}}
""".strip()


def _library_single_system_prompt(category: str) -> str:
    return f"""
你是表情包素材库单图整理器。当前图片已经位于 meme_manager_master 的 {category} 分类目录。
目录名是权威分类，不要移动或重新分类图片。请识别图片并只输出一个 JSON 对象。
不要输出 Markdown、解释或 JSON 数组；没有文字或标签时使用空字符串或空数组。
格式：{{"description":"不超过40字", "emotion":"主要情绪", "text":"图片文字", "tags":["关键词1"]}}
""".strip()


OUTGOING_DECISION_SYSTEM_PROMPT = """
你是聊天机器人的表情包决策器。请严格按以下顺序在一次输出中完成判断：
1. 判断机器人回复是否真的需要表情包；事实说明、长文、错误提示和无明显情绪时 should_send=false。
2. 如果需要，从候选图片所属分类中选择最符合语境的 category。
3. 从候选图片中选择最符合当前回复的一张 candidate_id。
只输出 JSON，不要 Markdown。
格式：
{"should_send":false, "category":"", "candidate_id":"", "confidence":0.0, "reason":"不超过30字"}
""".strip()


OUTGOING_DECISION_COMPACT_PROMPT = """
你是表情包发送决策器。
根据用户消息、机器人回复和候选图片，判断是否发送一张最匹配的表情包。
明确索要表情包或回复有明显情绪时可发送；事实说明、长文、报错或无明显情绪时不发送。
只输出 JSON：{"should_send":false,"category":"","candidate_id":"","confidence":0.0,"reason":"不超过20字"}
""".strip()


OUTGOING_CATEGORY_PROMPT = """
你是表情包情景分类器。
根据用户消息和机器人回复，判断是否发送表情包；若发送，只能从候选分类中选一个最合适的 category。
explicit_request=true 表示用户明确索要表情包，此时必须发送，should_send 必须为 true，只需选择最合适的 category。
只输出 JSON：{"should_send":false,"category":"","confidence":0.0,"reason":"不超过20字"}
""".strip()


LIBRARY_INDEX_VERSION = 3
LIBRARY_INDEX_PROMPT_VERSION = "library-batch-v3"


@dataclass(frozen=True)
class ImagePayload:
    content: bytes
    extension: str


class CaptureMixin:
    def __init__(self, context: Context, config: dict | None = None):
        if getattr(self, "_capture_initialized", False):
            return
        self._capture_initialized = True
        self.config = config or {}
        self.store = MemeStore.from_astrbot()
        self._semaphore = asyncio.Semaphore(self._int_config("max_concurrent", 2, 1, 8))
        self._save_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._health = MemeManagerHealth(
            status="plugin_missing",
            reason="尚未完成 meme_manager_master 健康检查。",
            data_root=self.store.root,
        )
        self._last_health_check = 0.0
        self._health_task: asyncio.Task | None = None
        self._library_task: asyncio.Task | None = None
        self._library_lock = asyncio.Lock()
        self._library_completed_key: tuple[str, tuple] | None = None
        self._library_retry_key: tuple[str, tuple] | None = None
        self._library_retry_at = 0.0
        self._library_index_state = {
            "status": "idle",
            "processed": 0,
            "total": 0,
            "classified": 0,
            "errors": 0,
            "message": "尚未开始目录索引",
        }
        self._last_auto_send: dict[str, float] = {}
        self._auto_send_claims: dict[str, float] = {}
        self._auto_send_umo_claims: dict[str, float] = {}
        self._auto_send_claim_lock = asyncio.Lock()
        self._agent_tool_guards: dict[str, float] = {}
        self._last_stolen_image: dict[str, Path] = {}
        self._stolen_image_by_event: dict[str, Path] = {}
        self._recent_meme_context: dict[str, tuple[float, Path, dict]] = {}
        self._meme_send_receipts: dict[str, tuple[float, Path, dict]] = {}
        self._explicit_meme_requests: dict[str, tuple[float, str]] = {}

    async def initialize(self) -> None:
        """Check the required plugin before accepting any image."""
        await self._refresh_health(force=True)
        self._health_task = asyncio.create_task(self._health_loop())

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(self._float_config("health_check_interval", 300, 10, 600))
            await self._refresh_health()

    async def _refresh_health(self, force: bool = False) -> MemeManagerHealth:
        self._refresh_store_for_active_pack()
        health = check_meme_manager_master_health(self.context, self.store)
        changed = health.status != self._health.status
        self._health = health
        self._last_health_check = time.monotonic()
        if health.ready:
            self._schedule_library_index()
        if force or changed:
            if health.ready:
                logger.info("[meme_manager_master] meme_manager_master 已就绪: %s", health.summary())
            else:
                logger.warning("[meme_manager_master] meme_manager_master 不可用: %s", health.summary())
        return health

    def _refresh_store_for_active_pack(self) -> bool:
        """Keep collection storage aligned with the manager's default pack."""
        try:
            from .backend.pack_resolver import resolve_pack_context

            context = resolve_pack_context()
            pack_dir = Path(context.get("pack_dir", self.store.root))
            if pack_dir.resolve() != self.store.root.resolve():
                self.store = MemeStore(pack_dir)
                return True
        except Exception:
            # The manager health check below will report an actionable state.
            return False
        return False

    async def _manager_ready(self) -> bool:
        store_changed = self._refresh_store_for_active_pack()
        interval = self._float_config("health_check_interval", 300, 10, 600)
        if store_changed or time.monotonic() - self._last_health_check >= interval:
            await self._refresh_health(force=store_changed)
        return self._health.ready

    def _recent_meme_sent(self, event: AstrMessageEvent) -> bool:
        """Return whether this chat recently received a meme from this plugin."""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        sent_at = self._last_auto_send.get(umo, 0.0)
        if not umo or not sent_at:
            return False
        window = self._float_config("meme_follow_up_window", 300, 10, 1800)
        return time.monotonic() - sent_at <= window

    def _remember_explicit_request(self, event: AstrMessageEvent) -> None:
        """Keep direct meme intent available across Agent continuation events."""
        message_text = self._event_text(event)
        if not explicit_meme_request(message_text):
            return
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if not umo:
            return
        self._explicit_meme_requests[umo] = (time.monotonic(), message_text)

    def _explicit_request_active(self, event: AstrMessageEvent) -> bool:
        """Return whether this event belongs to a recent direct meme request."""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if not umo:
            return False
        entry = self._explicit_meme_requests.get(umo)
        if entry is None:
            return False
        requested_at, _message_text = entry
        window = self._float_config("meme_follow_up_window", 300, 10, 1800)
        if time.monotonic() - requested_at > window:
            self._explicit_meme_requests.pop(umo, None)
            return False
        return True

    def _clear_explicit_request(self, event: AstrMessageEvent) -> None:
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if umo:
            self._explicit_meme_requests.pop(umo, None)

    def _remember_sent_meme(
        self,
        event: AstrMessageEvent,
        image_path: Path,
        details: dict | None = None,
    ) -> None:
        """Keep a short-lived semantic bridge for the next Agent turn."""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if not umo or not image_path.is_file():
            return
        try:
            image_details = dict(details or self._image_details(image_path))
        except Exception:
            image_details = {"filename": image_path.name, "category": image_path.parent.name}
        sent_at = time.monotonic()
        self._recent_meme_context[umo] = (sent_at, image_path, image_details)
        self._meme_send_receipts[event_identity(event)] = (
            sent_at,
            image_path,
            image_details,
        )
        if len(self._meme_send_receipts) > 1024:
            oldest = min(self._meme_send_receipts, key=self._meme_send_receipts.get)
            self._meme_send_receipts.pop(oldest, None)

    def _send_receipt_for_event(self, event: AstrMessageEvent) -> dict | None:
        """Return the current event's real meme-send receipt, if one exists."""
        key = event_identity(event)
        entry = self._meme_send_receipts.get(key)
        if entry is None:
            return None
        sent_at, _image_path, details = entry
        window = self._float_config("meme_follow_up_window", 300, 10, 1800)
        if time.monotonic() - sent_at > window:
            self._meme_send_receipts.pop(key, None)
            return None
        return dict(details)

    def _recent_meme_context_for_event(
        self,
        event: AstrMessageEvent,
    ) -> tuple[Path, dict] | None:
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        entry = self._recent_meme_context.get(umo)
        if not umo or entry is None:
            return None
        sent_at, image_path, details = entry
        window = self._float_config("meme_follow_up_window", 300, 10, 1800)
        if time.monotonic() - sent_at > window or not image_path.is_file():
            self._recent_meme_context.pop(umo, None)
            return None
        return image_path, details

    def _append_recent_meme_context(self, event: AstrMessageEvent, req) -> None:
        """Inject the send receipt and just-sent meme into the next Agent request.

        AstrBot decorates the outgoing message chain immediately before send;
        that chain is not guaranteed to be available in the next provider
        request.  A temporary user content part makes the association explicit
        without permanently polluting conversation history.
        """
        if getattr(req, "_meme_manager_master_context_added", False):
            return
        recent = self._recent_meme_context_for_event(event)
        extra_parts = getattr(req, "extra_user_content_parts", None)
        if not isinstance(extra_parts, list):
            return
        try:
            from astrbot.core.agent.message import TextPart
        except ImportError:
            logger.debug("[meme_manager_master] AstrBot TextPart unavailable; skip meme context bridge")
            return

        receipt = self._send_receipt_for_event(event)
        if receipt is None:
            receipt_text = (
                '<meme_send_receipt status="not_sent">\n'
                "当前事件没有插件生成的表情包发送凭证。禁止在回复中声称本轮已经发送了表情包；"
                "只有收到 status=sent 的凭证时才可以这样表述。\n"
                "</meme_send_receipt>"
            )
        else:
            receipt_text = (
                '<meme_send_receipt status="sent">\n'
                "当前事件存在插件生成的表情包发送凭证，可以据此确认本轮确实发送了表情包。\n"
                f"文件：{receipt.get('filename', '')}\n"
                "</meme_send_receipt>"
            )

        def append_temp_text(text: str) -> None:
            part = TextPart(text=text)
            mark_as_temp = getattr(part, "mark_as_temp", None)
            if callable(mark_as_temp):
                part = mark_as_temp()
            extra_parts.append(part)

        append_temp_text(receipt_text)
        if recent is not None:
            image_path, details = recent
            context_text = (
                "<recent_sent_meme>\n"
                "本插件刚刚在上一轮向当前会话发送了下面这张表情包。若用户提到“刚才的表情”、"
                "“这个表情”或“这张图”，必须优先指向它，不要引用更早历史中的其他图片。\n"
                f"文件：{image_path.name}\n"
                f"分类：{details.get('category', image_path.parent.name)}\n"
                f"画面描述：{details.get('description', '') or '暂无描述'}\n"
                f"情绪：{details.get('emotion', '') or '未知'}\n"
                f"图片文字：{details.get('text', '') or '无'}\n"
                f"标签：{', '.join(map(str, details.get('tags', []) or [])) or '无'}\n"
                "</recent_sent_meme>"
            )
            append_temp_text(context_text)
        try:
            setattr(req, "_meme_manager_master_context_added", True)
        except Exception:
            pass
        logger.debug(
            "[meme_manager_master] injected meme receipt/context recent=%s",
            recent is not None,
        )

    async def _claim_auto_send(
        self,
        event: AstrMessageEvent,
        *,
        force: bool = False,
    ) -> bool:
        """Atomically claim one event and one chat cooldown window."""
        key = event_identity(event)
        async with self._auto_send_claim_lock:
            now = time.monotonic()
            if key in self._auto_send_claims:
                logger.debug("[meme_manager_master] 跳过同一事件的重复表情包发送 event=%s", key)
                return False
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            cooldown = self._float_config("auto_send_cooldown", 30, 0, 3600)
            if not force and umo and cooldown:
                last_claim = max(
                    self._last_auto_send.get(umo, 0.0),
                    self._auto_send_umo_claims.get(umo, 0.0),
                )
                if now - last_claim < cooldown:
                    logger.debug("[meme_manager_master] 跳过同一会话的并发自动发送 umo=%s", umo)
                    return False
            self._auto_send_claims[key] = now
            if umo:
                self._auto_send_umo_claims[umo] = now
            if len(self._auto_send_claims) > 1024:
                oldest = min(self._auto_send_claims, key=self._auto_send_claims.get)
                self._auto_send_claims.pop(oldest, None)
            if len(self._auto_send_umo_claims) > 1024:
                oldest_umo = min(
                    self._auto_send_umo_claims,
                    key=self._auto_send_umo_claims.get,
                )
                self._auto_send_umo_claims.pop(oldest_umo, None)
            return True

    def _arm_agent_tool_guard(self, event: AstrMessageEvent) -> None:
        """Stop the same agent turn from drawing a second image after meme delivery."""
        now = time.monotonic()
        self._agent_tool_guards[event_identity(event)] = now + 15.0
        for key, expires_at in list(self._agent_tool_guards.items()):
            if expires_at <= now:
                self._agent_tool_guards.pop(key, None)

    def _agent_tool_guard_active(self, event: AstrMessageEvent) -> bool:
        now = time.monotonic()
        key = event_identity(event)
        expires_at = self._agent_tool_guards.get(key, 0.0)
        for expired_key, expired_at in list(self._agent_tool_guards.items()):
            if expired_at <= now:
                self._agent_tool_guards.pop(expired_key, None)
        return expires_at > now

    def _clear_agent_tool_guard(self, event: AstrMessageEvent) -> None:
        self._agent_tool_guards.pop(event_identity(event), None)

    def _rewrite_unverified_meme_claim(
        self,
        event: AstrMessageEvent,
        chain: list,
    ) -> None:
        """Prevent a generated reply from claiming a meme was sent without a receipt."""
        if self._send_receipt_for_event(event) is not None:
            return
        changed = False
        for component in chain:
            if not hasattr(component, "text"):
                continue
            text = str(getattr(component, "text", "") or "")
            if not contains_meme_send_claim(text):
                continue
            component.text = "我还没有成功发送表情包。"
            changed = True
        if changed:
            logger.warning(
                "[meme_manager_master] blocked unverified meme-send claim because no send receipt exists"
            )

    @staticmethod
    def _disable_default_llm(event: AstrMessageEvent) -> None:
        """Keep plugin LLM calls available while skipping AstrBot's default Agent."""
        should_call_llm = getattr(event, "should_call_llm", None)
        if callable(should_call_llm):
            should_call_llm(False)
        else:
            event.stop_event()

    async def _handle_explicit_meme_request(
        self,
        event: AstrMessageEvent,
        message_text: str,
    ) -> None:
        """Handle a direct meme request before the default Agent can use tools."""
        self._clear_explicit_request(event)
        setattr(event, "_meme_manager_master_explicit_handled", True)
        if not await self._manager_ready():
            event.set_result(
                event.plain_result("本地表情包管理器当前不可用，暂时无法发送表情包。")
            )
            self._disable_default_llm(event)
            return
        if not await self._claim_auto_send(event, force=True):
            self._disable_default_llm(event)
            return

        image_path = await self._choose_outgoing_meme_from_index(
            event,
            message_text,
            force_send=True,
        )
        if image_path is None:
            event.set_result(
                event.plain_result("本地表情包库暂时没有找到合适的表情包。")
            )
            self._disable_default_llm(event)
            logger.info("[meme_manager_master] explicit meme request handled without a local match")
            return

        umo = str(getattr(event, "unified_msg_origin", "") or "")
        self._arm_agent_tool_guard(event)
        event.set_result(
            event.chain_result(
                [
                    Comp.Plain("找到了一个合适的表情包，发给你～"),
                    Comp.Image.fromFileSystem(str(image_path)),
                ]
            )
        )
        if umo:
            self._last_auto_send[umo] = time.monotonic()
        self._remember_sent_meme(event, image_path)
        self._disable_default_llm(event)
        logger.info(
            "[meme_manager_master] explicit meme request handled before default Agent file=%s",
            image_path,
        )

    def _schedule_library_index(self) -> None:
        """Schedule an idempotent scan when meme_manager_master is healthy."""
        if not self._bool_config("library_index_enabled", False):
            return
        provider_id = configured_provider_id(
            self.config,
            "library_index_provider_id",
            "vision_provider_id",
        )
        # A background task has no chat event from which to infer a provider.
        if not provider_id:
            return
        if self._library_task is not None and not self._library_task.done():
            return
        source_signature = self._library_source_signature()
        run_key = (provider_id, source_signature)
        if self._library_catalogs_are_complete(provider_id, source_signature):
            self._library_completed_key = run_key
            return
        now = time.monotonic()
        if run_key == self._library_completed_key:
            return
        if run_key == self._library_retry_key and now < self._library_retry_at:
            return
        self._library_task = asyncio.create_task(self._ensure_library_index())
        self._library_task.add_done_callback(self._log_library_task_failure)

    def _library_source_signature(self) -> tuple:
        """Return a cheap signature for image files that need indexing."""
        signature = []
        for category in sorted(self.store.directory_categories()):
            for path in self.store.image_paths(category):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                try:
                    digest = self.store.image_digest(path)
                except OSError:
                    continue
                signature.append((category, path.name, digest))
        return tuple(signature)

    def _library_catalogs_are_complete(
        self,
        provider_id: str,
        source_signature: tuple,
    ) -> bool:
        """Avoid starting a background model task for an already indexed pack."""
        categories = sorted(self.store.directory_categories())
        if not categories or not source_signature:
            return False
        expected = self._library_index_metadata(provider_id)
        by_category: dict[str, list[tuple[str, str]]] = {}
        for category, filename, digest in source_signature:
            by_category.setdefault(category, []).append((filename, digest))
        for category in categories:
            catalog = self.store.load_catalog(category)
            if not catalog.get("classification_index_complete"):
                return False
            if not index_metadata_matches(catalog, expected):
                return False
            if catalog.get("classification_index_file_total") != len(
                by_category.get(category, [])
            ):
                return False
            by_digest = {
                str(item.get("sha256")): item
                for item in catalog.get("items", [])
                if isinstance(item, dict) and item.get("sha256")
            }
            for _filename, digest in by_category.get(category, []):
                if not self._catalog_entry_is_current(by_digest.get(digest), provider_id):
                    return False
        return True

    def _category_content_signature(self, category: str) -> tuple[tuple[str, str], ...]:
        """Return content identities used to detect writes during indexing."""
        signature: list[tuple[str, str]] = []
        for path in self.store.image_paths(category):
            try:
                signature.append((path.name, self.store.image_digest(path)))
            except OSError:
                continue
        return tuple(signature)

    def _schedule_library_retry(self, provider_id: str) -> None:
        self._library_retry_key = (
            provider_id,
            self._library_source_signature(),
        )
        self._library_retry_at = time.monotonic() + max(
            self._float_config("health_check_interval", 300, 10, 600),
            60,
        )

    @staticmethod
    def _log_library_task_failure(task: asyncio.Task) -> None:
        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return
        if exception:
            logger.error("[meme_manager_master] 后台表情包索引任务异常: %s", exception)

    async def on_message(
        self,
        event: AstrMessageEvent,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        """Queue group images for background recognition and storage.

        AstrBot's pipeline may forward extra handler arguments.  This listener
        only needs the event, so accept and ignore those compatibility args.
        """
        self._remember_explicit_request(event)
        if getattr(event, "_meme_manager_master_manual", False):
            return
        if not self._bool_config("enabled", True):
            return

        if not await self._manager_ready():
            return
        if not group_id_from_event(event):
            return
        if not whitelist_allows(event, self._whitelist()):
            return

        try:
            components = event.get_messages()
        except Exception:
            logger.warning("[meme_manager_master] 无法读取消息链", exc_info=True)
            return
        sources = extract_image_sources(components)
        limit = self._int_config("max_images_per_message", 2, 1, 6)
        if not sources:
            return

        text = self._event_text(event)
        outline = self._event_outline(event)
        task = asyncio.create_task(self._process_and_maybe_send(event, sources[:limit], text, outline))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._log_task_failure)

    async def steal_command(self, event: AstrMessageEvent):
        """Process images attached to the same message as /偷取 immediately."""
        setattr(event, "_meme_manager_master_manual", True)
        if not await self._manager_ready():
            yield event.plain_result("meme_manager_master 当前不可用，暂时无法偷取。")
            return
        if not group_id_from_event(event):
            yield event.plain_result("/偷取 只允许在群聊中使用。")
            return
        if not whitelist_allows(event, self._whitelist()):
            yield event.plain_result("当前群不在表情包偷取白名单中。")
            return
        try:
            sources = extract_image_sources(event.get_messages())
        except Exception:
            sources = []
        if not sources:
            yield event.plain_result("请在同一条消息中附带图片后发送 /偷取。")
            return

        limit = self._int_config("max_images_per_message", 2, 1, 6)
        text = self._event_text(event)
        outline = self._event_outline(event)
        results = await self._process_batch(event, sources[:limit], text, outline)
        await self._send_stolen_image_proactively(event, results)
        event.stop_event()
        summary = {
            "saved": "已保存",
            "duplicate": "已存在",
            "not_meme": "判定为普通图片",
            "unavailable": "图片无法读取",
            "error": "处理失败",
        }
        counts: dict[str, int] = {}
        for result in results:
            counts[result] = counts.get(result, 0) + 1
        details = "，".join(f"{summary.get(key, key)} {value} 张" for key, value in counts.items())
        yield event.plain_result(f"偷取处理完成：{details}")

    async def _process_and_maybe_send(
        self,
        event: AstrMessageEvent,
        sources: list[str],
        message_text: str,
        message_outline: str,
    ) -> None:
        results = await self._process_batch(event, sources, message_text, message_outline)
        await self._send_stolen_image_proactively(event, results)

    async def _send_stolen_image_proactively(
        self,
        event: AstrMessageEvent,
        results: list[str],
    ) -> None:
        """Send the latest captured image through an independent message path."""
        event_key = event_identity(event)
        if not self._bool_config("proactive_send_after_steal", False):
            self._stolen_image_by_event.pop(event_key, None)
            return
        if not any(status in {"saved", "duplicate"} for status in results):
            self._stolen_image_by_event.pop(event_key, None)
            return
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        image_path = self._stolen_image_by_event.pop(event_key, None)
        if not umo or image_path is None or not image_path.is_file():
            return
        try:
            message_chain = MessageChain().file_image(str(image_path))
            await self.context.send_message(umo, message_chain)
            self._remember_sent_meme(event, image_path)
            logger.info("[meme_manager_master] 偷取后主动发送表情包 path=%s", image_path)
        except Exception as exc:
            logger.warning("[meme_manager_master] 偷取后主动发送失败: %s", exc, exc_info=True)

    async def send_last_stolen_image(self, event: AstrMessageEvent):
        """Send the most recently saved meme from this chat session."""
        if not await self._manager_ready():
            yield event.plain_result("meme_manager_master 当前不可用，暂时无法发送表情包。")
            return
        if not group_id_from_event(event):
            yield event.plain_result("发送表情包只允许在群聊中使用。")
            return
        if not whitelist_allows(event, self._whitelist()):
            yield event.plain_result("当前群不在表情包偷取白名单中。")
            return

        umo = str(getattr(event, "unified_msg_origin", "") or "")
        image_path = self._last_stolen_image.get(umo)
        if image_path is None or not image_path.is_file():
            yield event.plain_result("当前会话还没有可发送的表情包，请先发送 /偷取 [图片]。")
            return

        event.stop_event()
        self._remember_sent_meme(event, image_path)
        yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])

    async def status(self, event: AstrMessageEvent):
        """显示 meme_manager_master 依赖插件的加载与数据目录状态。"""
        health = await self._refresh_health(force=True)
        yield event.plain_result(health.summary())

    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        """Replace meme_manager_master's marker sender with this plugin's sender."""
        if getattr(event, "_meme_manager_master_explicit_handled", False):
            return
        result = event.get_result()
        chain = getattr(result, "chain", None) if result else None
        if not chain:
            return
        chain = drop_empty_text_components(list(chain))
        result.chain = chain
        if not chain:
            return

        plain_texts: list[str] = []
        marked_categories: list[str] = []
        for component in chain:
            if not hasattr(component, "text"):
                continue
            original = str(getattr(component, "text", "") or "")
            marked_categories.extend(extract_meme_markers(original))
            cleaned = strip_meme_markers(original)
            if cleaned != original:
                component.text = cleaned
            if cleaned:
                plain_texts.append(cleaned)
        event_text = self._event_text(event)
        explicit_request_fallback = self._explicit_request_active(event)
        if explicit_request_fallback:
            # Consume the bridge here so an unrelated later reply in this chat
            # cannot inherit the previous direct-send intent.
            self._clear_explicit_request(event)
        force_send = (
            explicit_meme_request(event_text)
            or explicit_request_fallback
            or is_meme_follow_up_request(
                event_text,
                recent_meme=self._recent_meme_sent(event),
            )
        )

        # Marker cleanup always happens, even if our own sender is disabled.
        if (
            not self._bool_config("auto_send_enabled", True)
            or (not plain_texts and not marked_categories and not force_send)
            or self._is_control_command(event)
            or not await self._manager_ready()
        ):
            self._rewrite_unverified_meme_claim(event, chain)
            return

        umo = str(getattr(event, "unified_msg_origin", "") or "")
        cooldown = self._float_config("auto_send_cooldown", 30, 0, 3600)
        if (
            cooldown
            and not force_send
            and time.monotonic() - self._last_auto_send.get(umo, 0) < cooldown
        ):
            self._rewrite_unverified_meme_claim(event, chain)
            return

        probability = self._float_config("auto_send_probability", 35, 0, 100)
        if not force_send and (probability <= 0 or random.random() * 100 >= probability):
            self._rewrite_unverified_meme_claim(event, chain)
            return
        if not await self._claim_auto_send(event, force=force_send):
            self._rewrite_unverified_meme_claim(event, chain)
            return
        image_path = await self._choose_outgoing_meme_from_index(
            event,
            "\n".join(plain_texts),
            force_send=force_send,
            preferred_categories=marked_categories,
        )
        if image_path is None:
            self._rewrite_unverified_meme_claim(event, chain)
            logger.debug("[meme_manager_master] 情景模型未选择可发送表情包")
            return
        details = self._image_details(image_path)
        if force_send:
            confirmation = "找到了一个合适的表情包，发给你～"
            replaced = False
            for component in chain:
                if not hasattr(component, "text"):
                    continue
                component.text = confirmation if not replaced else ""
                replaced = True
        result.chain = drop_empty_text_components(chain) + [
            Comp.Image.fromFileSystem(str(image_path))
        ]
        if umo:
            self._last_auto_send[umo] = time.monotonic()
        self._remember_sent_meme(event, image_path, details)
        self._arm_agent_tool_guard(event)
        logger.info(
            "[meme_manager_master] 已锁定表情包，等待正文发送完成 source=%s category=%s file=%s "
            "description=%s emotion=%s tags=%s",
            "explicit_request" if force_send else (
                "scene_with_category_hint" if marked_categories else "scene"
            ),
            details["category"],
            details["filename"],
            details["description"],
            details["emotion"],
            details["tags"],
        )

    async def on_llm_request(self, event: AstrMessageEvent, req) -> None:
        """Inject recent meme context and remove image-producing Agent tools."""
        self._remember_explicit_request(event)
        message_text = self._event_text(event)
        if explicit_meme_request(message_text):
            await self._handle_explicit_meme_request(event, message_text)
            return
        self._append_recent_meme_context(event, req)
        if not should_block_agent_tool_for_meme_request(
            "astrbot_execute_python",
            self._event_text(event),
            guard_active=self._agent_tool_guard_active(event),
        ):
            return

        tool_set = getattr(req, "func_tool", None)
        if tool_set is None:
            return
        get_tool = getattr(tool_set, "get_tool", None)
        if callable(get_tool) and get_tool("astrbot_execute_python") is None:
            return
        remove_tool = getattr(tool_set, "remove_tool", None)
        if callable(remove_tool):
            remove_tool("astrbot_execute_python")
        elif isinstance(getattr(tool_set, "tools", None), list):
            tool_set.tools = [
                tool
                for tool in tool_set.tools
                if getattr(tool, "name", "") != "astrbot_execute_python"
            ]
        else:
            return
        logger.info(
            "[meme_manager_master] removed astrbot_execute_python before LLM request"
        )

    async def on_using_llm_tool(self, event: AstrMessageEvent, tool, tool_args=None) -> None:
        """Prevent the main Agent from drawing/sending again after a local meme."""
        tool_name = str(
            getattr(tool, "name", "")
            or (tool.get("name", "") if isinstance(tool, dict) else "")
            or (tool if isinstance(tool, str) else "")
        ).strip()
        guard_active = self._agent_tool_guard_active(event)
        if not should_block_agent_tool_for_meme_request(
            tool_name,
            self._event_text(event),
            guard_active=guard_active,
        ):
            return
        self._disable_default_llm(event)
        event.stop_event()
        logger.info(
            "[meme_manager_master] blocked agent tool after local meme send tool=%s",
            tool_name,
        )

    async def _process_one(
        self,
        event: AstrMessageEvent,
        source: str,
        message_text: str,
        message_outline: str,
    ) -> str:
        results = await self._process_batch(
            event, [source], message_text, message_outline
        )
        return results[0] if results else "error"

    async def _process_batch(
        self,
        event: AstrMessageEvent,
        sources: list[str],
        message_text: str,
        message_outline: str,
    ) -> list[str]:
        """Process all new images in one message with two batched model calls."""
        async with self._semaphore:
            statuses = ["error"] * len(sources)
            loaded: list[tuple[int, ImagePayload, Path]] = []
            for index, source in enumerate(sources):
                try:
                    payload = await self._load_image(source)
                except Exception:
                    payload = None
                if payload is None:
                    statuses[index] = "unavailable"
                    continue
                threshold = self._perceptual_duplicate_threshold()
                duplicate_path = self.store.find_duplicate(payload.content, threshold)
                if duplicate_path is not None:
                    logger.debug("[meme_manager_master] 图片在识别前已存在，跳过模型调用")
                    statuses[index] = "duplicate"
                    duplicate_category = duplicate_path.parent.name
                    record_capture_event(
                        self.store.root,
                        category=duplicate_category,
                        filename=duplicate_path.name,
                        digest=self.store.image_digest(duplicate_path),
                        status="duplicate",
                        duplicate_of=f"{duplicate_category}/{duplicate_path.name}",
                    )
                    continue
                if any(
                    self.store.is_similar(payload.content, previous.content, threshold)
                    for _previous_index, previous, _previous_path in loaded
                ):
                    logger.debug("[meme_manager_master] current message contains a perceptual duplicate")
                    statuses[index] = "duplicate"
                    continue
                temp_path = self.store.make_temp_file(payload.content, payload.extension)
                loaded.append((index, payload, temp_path))
            if not loaded:
                return statuses

            try:
                categories = self.store.available_categories()
                image_paths = [
                    (index, temp_path) for index, _payload, temp_path in loaded
                ]
                try:
                    if len(image_paths) == 1:
                        index, temp_path = image_paths[0]
                        visions = {
                            index: await self._recognize_image(event, temp_path, message_text)
                        }
                    else:
                        visions = await self._recognize_batch(event, image_paths, message_text)
                except Exception as exc:
                    logger.warning(
                        "[meme_manager_master] 视觉批量调用失败，回退逐张识别: %s",
                        exc,
                    )
                    visions = {
                        index: await self._recognize_image(event, temp_path, message_text)
                        for index, temp_path in image_paths
                    }
                accepted = {}
                for index, vision in visions.items():
                    if vision.get("vision_error"):
                        statuses[index] = "unavailable"
                        continue
                    if not self._should_skip(vision):
                        accepted[index] = vision
                for index in visions:
                    if index not in accepted:
                        if statuses[index] == "error":
                            statuses[index] = "not_meme"
                            logger.info(
                                "[meme_manager_master] 图片未被识别为表情包，跳过保存 index=%s",
                                index,
                            )
                if not accepted:
                    return statuses

                try:
                    if len(accepted) == 1:
                        index, vision = next(iter(accepted.items()))
                        scenes = {
                            index: await self._classify_scene(
                                event,
                                vision,
                                categories,
                                message_text,
                                message_outline,
                            )
                        }
                    else:
                        scenes = await self._classify_batch(
                            event,
                            accepted,
                            categories,
                            message_text,
                            message_outline,
                        )
                except Exception as exc:
                    logger.warning(
                        "[meme_manager_master] 情景批量调用失败，回退逐张分类: %s",
                        exc,
                    )
                    scenes = {
                        index: await self._classify_scene(
                            event,
                            vision,
                            categories,
                            message_text,
                            message_outline,
                        )
                        for index, vision in accepted.items()
                    }
                payload_by_index = {index: payload for index, payload, _path in loaded}
                fallback = str(self.config.get("fallback_category", "confused"))
                for index, vision in accepted.items():
                    scene = scenes.get(index, {})
                    category = normalize_category(scene.get("category"), categories, fallback)
                    payload = payload_by_index[index]
                    async with self._save_lock:
                        result = self.store.save_image(
                            payload.content,
                            category,
                            payload.extension,
                            self._perceptual_duplicate_threshold(),
                        )
                        if result.status in {"saved", "duplicate"}:
                            umo = str(getattr(event, "unified_msg_origin", "") or "")
                            if umo:
                                self._last_stolen_image[umo] = result.path
                            self._stolen_image_by_event[event_identity(event)] = result.path
                        statuses[index] = result.status
                        if result.status == "saved":
                            catalog_entry = self._catalog_entry_from_vision(
                                result.path, category, vision, scene
                            )
                            catalog_entry["perceptual_hash"] = self.store.image_perceptual_hash(
                                result.path
                            )
                            self.store.upsert_catalog_entry(
                                category,
                                catalog_entry,
                            )
                            record_capture_event(
                                self.store.root,
                                category=category,
                                filename=result.path.name,
                                digest=result.digest,
                                status="pending",
                            )
                            logger.info(
                                "[meme_manager_master] 已收集表情包 category=%s path=%s",
                                category,
                                result.path,
                            )
                        else:
                            if result.status == "duplicate":
                                duplicate_category = result.path.parent.name
                                record_capture_event(
                                    self.store.root,
                                    category=duplicate_category,
                                    filename=result.path.name,
                                    digest=result.digest,
                                    status="duplicate",
                                    duplicate_of=f"{duplicate_category}/{result.path.name}",
                                )
                            logger.debug("[meme_manager_master] 跳过重复表情包 path=%s", result.path)
                return statuses
            except Exception:
                logger.error("[meme_manager_master] 批量处理群聊图片失败", exc_info=True)
                return [status if status != "error" else "error" for status in statuses]
            finally:
                for _index, _payload, temp_path in loaded:
                    self.store.remove_temp_file(temp_path)

    async def _recognize_batch(
        self,
        event: AstrMessageEvent,
        images: list[tuple[int, Path]],
        message_text: str,
    ) -> dict[int, dict]:
        prompt = "\n".join(
            [
                "同一条消息中的图片如下，请逐张识别并保留 image id：",
                *[f"image_{index}: {path.name}" for index, path in images],
                f"消息语境：{message_text[:500]}",
            ]
        )
        response = await self._generate(
            event,
            prompt,
            image_urls=[str(path) for _index, path in images],
            provider_id=configured_provider_id(self.config, "vision_provider_id"),
            system_prompt=VISION_BATCH_SYSTEM_PROMPT,
        )
        parsed = parse_model_json(response)
        items = parsed.get("items", [])
        if not isinstance(items, list):
            raise ValueError("batch vision response items is not a list")
        result: dict[int, dict] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            match = re.fullmatch(r"image_(\d+)", str(item.get("id", "")))
            if match:
                result[int(match.group(1))] = item
        expected_indices = {index for index, _path in images}
        if not complete_batch_indices(result, expected_indices):
            raise ValueError("batch vision response is missing image ids")
        return result

    async def _classify_batch(
        self,
        event: AstrMessageEvent,
        visions: dict[int, dict],
        categories: set[str],
        message_text: str,
        message_outline: str,
    ) -> dict[int, dict]:
        prompt = "\n".join(
            [
                f"当前消息文字：{message_text[:500]}",
                f"消息概要：{message_outline[:500]}",
                "请为以下每张图片分别选择分类并保留 image id：",
                *[f"image_{index}: {vision}" for index, vision in sorted(visions.items())],
            ]
        )
        response = await self._generate(
            event,
            prompt,
            image_urls=[],
            provider_id=configured_provider_id(self.config, "scene_provider_id"),
            system_prompt=_scene_batch_system_prompt(categories),
        )
        parsed = parse_model_json(response)
        items = parsed.get("items", [])
        if not isinstance(items, list):
            raise ValueError("batch scene response items is not a list")
        result: dict[int, dict] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            match = re.fullmatch(r"image_(\d+)", str(item.get("id", "")))
            if match:
                result[int(match.group(1))] = item
        if not complete_batch_indices(result, set(visions)):
            raise ValueError("batch scene response is missing image ids")
        return result

    async def _ensure_library_index(self) -> None:
        """Index missing or stale images without changing their category folders."""
        if self._library_lock.locked():
            return
        async with self._library_lock:
            self._library_index_state.update(
                status="running",
                processed=0,
                total=0,
                classified=0,
                errors=0,
                message="正在检查分类目录……",
            )
            categories = sorted(self.store.directory_categories())
            total = sum(len(self.store.image_paths(category)) for category in categories)
            self._library_index_state["total"] = total
            if not total:
                self._library_index_state.update(status="idle", message="没有待索引图片")
                return
            provider_id = configured_provider_id(
                self.config,
                "library_index_provider_id",
                "vision_provider_id",
            )
            if not provider_id:
                self._library_index_state.update(
                    status="blocked", message="未配置目录索引视觉模型"
                )
                return
            run_signature = self._library_source_signature()
            processed = 0
            classified = 0
            errors = 0
            progress_step = self._int_config("library_index_progress_step", 5, 1, 50)
            for category in categories:
                paths = self.store.image_paths(category)
                old_catalog = self.store.load_catalog(category)
                by_digest = {
                    str(item.get("sha256")): item
                    for item in old_catalog.get("items", [])
                    if isinstance(item, dict) and item.get("sha256")
                }
                index_metadata = self._library_index_metadata(provider_id)
                catalog_is_current = index_metadata_matches(
                    old_catalog, index_metadata
                )
                records: list[tuple[Path, dict]] = []
                pending: list[tuple[Path, str]] = []
                category_signature: list[tuple[str, str]] = []
                for path in paths:
                    digest = self.store.image_digest(path)
                    category_signature.append((path.name, digest))
                    old_entry = by_digest.get(digest)
                    if catalog_is_current and self._catalog_entry_is_current(
                        old_entry, provider_id
                    ):
                        metadata = dict(old_entry)
                        metadata.update({
                            "category": category,
                            "sha256": digest,
                            "perceptual_hash": self.store.image_perceptual_hash(path),
                        })
                        records.append((path, metadata))
                        processed += 1
                    else:
                        pending.append((path, digest))

                batch_size = self._int_config("library_index_batch_size", 6, 1, 12)
                for start in range(0, len(pending), batch_size):
                    batch = pending[start : start + batch_size]
                    batch_paths = [path for path, _digest in batch]
                    classified += len(batch)
                    try:
                        batch_results = await self._describe_library_batch(
                            None, batch_paths, category, provider_id
                        )
                    except Exception as exc:
                        logger.debug(
                            "[meme_manager_master] 自动索引批次失败，改用逐图识别 category=%s count=%s: %s",
                            category,
                            len(batch),
                            exc,
                        )
                        batch_results = {}
                        for path in batch_paths:
                            try:
                                batch_results.update(
                                    await self._describe_library_single(
                                        None, path, category, provider_id
                                    )
                                )
                            except Exception as single_exc:
                                logger.debug(
                                    "[meme_manager_master] single-image index fallback failed path=%s: %s",
                                    path,
                                    single_exc,
                                )
                        if not batch_results:
                            logger.warning(
                                "[meme_manager_master] 逐图识别也失败，停止本轮并进入退避 category=%s count=%s",
                                category,
                                len(batch),
                            )
                            self._schedule_library_retry(provider_id)
                            return
                    for path, digest in batch:
                        metadata = batch_results.get(path)
                        if metadata is None:
                            errors += 1
                            metadata = {
                                "description": "待重新识别",
                                "emotion": "未知",
                                "text": "",
                                "tags": [],
                                "indexed": False,
                            }
                        metadata.update({
                            "category": category,
                            "sha256": digest,
                            "perceptual_hash": self.store.image_perceptual_hash(path),
                            **index_metadata,
                        })
                        records.append((path, metadata))
                        processed += 1
                    if processed == total or processed % progress_step == 0:
                        logger.info(
                            "[meme_manager_master] 自动索引进度 %s 分类=%s 批量=%s",
                            self._progress_text(processed, total, errors),
                            category,
                            len(batch),
                        )

                async with self._save_lock:
                    if self._category_content_signature(category) != tuple(category_signature):
                        errors += 1
                        logger.info(
                            "[meme_manager_master] 索引期间分类发生变化，跳过写入并稍后重试 category=%s",
                            category,
                        )
                        continue
                    mapping = (
                        self.store.renumber_category(category)
                        if self._bool_config("library_index_rename_files", True)
                        else {path: path for path, _metadata in records}
                    )
                    entries = []
                    for old_path, metadata in records:
                        new_path = mapping.get(old_path, old_path)
                        entry = dict(metadata)
                        entry.update({"id": new_path.stem, "filename": new_path.name})
                        entries.append(entry)
                    current_catalog = self.store.load_catalog(category)
                    category_complete = all(
                        bool(entry.get("indexed")) for entry in entries
                    )
                    indexed_at = (
                        int(current_catalog.get("classification_indexed_at") or time.time())
                        if catalog_is_current and not pending
                        else int(time.time())
                    )
                    catalog_metadata = {
                        **index_metadata,
                        "classification_index_complete": category_complete,
                        "classification_indexed_at": indexed_at,
                        "classification_index_file_total": len(entries),
                    }
                    if catalog_needs_write(current_catalog, entries, catalog_metadata):
                        self.store.write_catalog(category, entries, catalog_metadata)
                    if category_complete:
                        mark_capture_events_indexed(
                            self.store.root,
                            category=category,
                            digests={str(entry.get("sha256")) for entry in entries},
                        )
                    self._library_index_state.update(
                        processed=processed,
                        classified=classified,
                        errors=errors,
                        message=f"正在处理 {category}",
                    )
            final_signature = self._library_source_signature()
            final_key = (provider_id, final_signature)
            if errors:
                self._schedule_library_retry(provider_id)
            elif final_signature != run_signature:
                # A file was added/changed while the scan was running. Keep
                # the completed key at the start signature so the next health
                # check schedules another pass for the new source set.
                self._library_completed_key = (provider_id, run_signature)
                self._library_retry_key = None
                self._library_retry_at = 0.0
            else:
                self._library_completed_key = final_key
                self._library_retry_key = None
                self._library_retry_at = 0.0
            logger.info(
                "[meme_manager_master] 自动索引检查完成 total=%s newly_classified=%s errors=%s",
                total,
                classified,
                errors,
            )
            self._library_index_state.update(
                status="completed" if not errors else "completed_with_errors",
                processed=processed,
                classified=classified,
                errors=errors,
                message="目录索引完成" if not errors else "目录索引完成，但有图片待重试",
            )

    async def _describe_library_batch(
        self,
        event: AstrMessageEvent | None,
        image_paths: list[Path],
        category: str,
        provider_id: str,
    ) -> dict[Path, dict]:
        image_ids = {path: f"image_{index}" for index, path in enumerate(image_paths)}
        prompt = "\n".join(
            [
                f"分类目录：{category}",
                "请按候选图片的 id 返回结果，候选图片顺序如下：",
                *[f"{image_id}: {path.name}" for path, image_id in image_ids.items()],
            ]
        )
        response = await self._generate(
            event,
            prompt,
            image_urls=[str(path) for path in image_paths],
            provider_id=provider_id,
            system_prompt=_library_batch_system_prompt(category),
        )
        parsed = parse_model_json(response)
        if isinstance(parsed, dict):
            items = parsed.get("items", parsed.get("results", parsed))
        else:
            items = parsed
        return normalize_library_results(items, image_paths)

    async def _describe_library_single(
        self,
        event: AstrMessageEvent | None,
        image_path: Path,
        category: str,
        provider_id: str,
    ) -> dict[Path, dict]:
        response = await self._generate(
            event,
            f"分类目录：{category}\n请识别这张图片并返回描述、情绪、图片文字和标签。",
            image_urls=[str(image_path)],
            provider_id=provider_id,
            system_prompt=_library_single_system_prompt(category),
        )
        parsed = parse_model_json(response)
        items = parsed.get("items", parsed) if isinstance(parsed, dict) else parsed
        result = normalize_library_results(items, [image_path])
        if image_path not in result:
            raise ValueError("single-image index response cannot be matched")
        return result

    async def _choose_outgoing_meme_from_index(
        self,
        event: AstrMessageEvent,
        response_text: str,
        force_send: bool = False,
        preferred_categories: list[str] | None = None,
    ) -> Path | None:
        """Let the scene model choose a category, then select from its index locally."""
        descriptions = self.store.category_descriptions()
        preferred = set(preferred_categories or [])
        candidates = []
        for category in sorted(descriptions):
            if preferred and category not in preferred:
                continue
            catalog = self.store.load_catalog(category)
            indexed_count = sum(
                1
                for item in catalog.get("items", [])
                if isinstance(item, dict) and item.get("filename")
            )
            if indexed_count:
                candidates.append(
                    {
                        "category": category,
                        "description": str(descriptions.get(category, ""))[:100],
                        "indexed_count": indexed_count,
                    }
                )
        limit = self._int_config("auto_send_candidate_limit", 8, 2, 16)
        # Explicit requests must see every indexed category; random sampling
        # could otherwise omit the category the user explicitly requested.
        if len(candidates) > limit and not force_send and not preferred:
            candidates = random.sample(candidates, limit)
        if not candidates:
            logger.warning(
                "[meme_manager_master] 情景分析没有可用索引 category_hint=%s",
                sorted(preferred) or "none",
            )
            return None

        prompt = "\n".join(
            [
                f"用户:{self._event_text(event)[:300]}",
                f"回复:{response_text[:600]}",
                f"explicit_request={'true' if force_send else 'false'}",
                f"category_hint={','.join(sorted(preferred)) or 'none'}",
                "候选(category|说明|索引数量):",
                *[
                    f"{item['category']}|{item['description']}|{item['indexed_count']}"
                    for item in candidates
                ],
            ]
        )
        try:
            response = await self._generate(
                event,
                prompt,
                image_urls=[],
                provider_id=configured_provider_id(
                    self.config,
                    "reply_scene_provider_id",
                    "scene_provider_id",
                ),
                system_prompt=OUTGOING_CATEGORY_PROMPT,
            )
            choice = parse_model_json(response)
            reason = str(choice.get("reason", "") or "")[:80]
            confidence = choice.get("confidence", "")
            model_should_send = self._model_bool(
                choice.get("should_send"), default=False
            )
            if force_send and not model_should_send:
                logger.info(
                    "[meme_manager_master] 明确请求覆盖模型的不发送判断，继续选择分类"
                )
            if not force_send and not model_should_send:
                logger.info(
                    "[meme_manager_master] 情景分析决定不发送 confidence=%s reason=%s",
                    confidence,
                    reason,
                )
                return None

            category = str(
                choice.get("category") or choice.get("candidate_id") or ""
            ).strip()
            selected = next(
                (item for item in candidates if item["category"] == category),
                None,
            )
            if selected is None:
                logger.warning(
                    "[meme_manager_master] 情景分析选择了不存在的分类 category=%s reason=%s",
                    category,
                    reason,
                )
                return None

            image_path = self.store.pick_indexed_image(category)
            if image_path is None:
                logger.warning(
                    "[meme_manager_master] 分类索引没有可用图片 category=%s",
                    category,
                )
                return None
            details = self._image_details(image_path)
            logger.info(
                "[meme_manager_master] 情景分析决定发送 category=%s confidence=%s "
                "reason=%s description=%s indexed_count=%s",
                category,
                confidence,
                reason,
                details["description"],
                selected["indexed_count"],
            )
            return image_path
        except Exception as exc:
            logger.warning("[meme_manager_master] 分类索引发送决策失败，不发送表情包: %s", exc)
            return None

    async def _choose_outgoing_meme_legacy(
        self,
        event: AstrMessageEvent,
        response_text: str,
        force_send: bool = False,
        preferred_categories: list[str] | None = None,
    ) -> Path | None:
        """Use one multimodal call for should_send, category, and candidate choice."""
        descriptions = self.store.category_descriptions()
        preferred = set(preferred_categories or [])
        candidates = []
        for category in sorted(descriptions):
            if preferred and category not in preferred:
                continue
            paths = self.store.image_paths(category)
            if not paths:
                continue
            catalog = self.store.load_catalog(category)
            indexed = {
                str(item.get("filename")): item
                for item in catalog.get("items", [])
                if isinstance(item, dict)
            }
            # One representative per category keeps the single request bounded.
            path = random.choice(paths)
            item = indexed.get(path.name, {})
            raw_tags = item.get("tags", [])
            if isinstance(raw_tags, str):
                raw_tags = [raw_tags]
            if not isinstance(raw_tags, list):
                raw_tags = []
            candidates.append(
                {
                    "id": str(item.get("id") or path.stem),
                    "category": category,
                    "filename": path.name,
                    "description": str(item.get("description") or "未建立索引"),
                    "emotion": str(item.get("emotion") or "未知"),
                    "tags": [str(tag)[:30] for tag in raw_tags[:8]],
                    "path": path,
                }
            )
        limit = self._int_config("auto_send_candidate_limit", 8, 2, 16)
        if len(candidates) > limit:
            candidates = random.sample(candidates, limit)
        if not candidates:
            return None
        try:
            prompt = "\n".join(
                [
                    f"用户:{self._event_text(event)[:300]}",
                    f"回复:{response_text[:600]}",
                    f"explicit_request={'true' if force_send else 'false'}",
                    f"category_hint={','.join(sorted(preferred)) or 'none'}",
                    "候选(id|分类|描述|情绪|标签):",
                    *[
                        f"{item['id']}|{item['category']}|{item['description'][:80]}|"
                        f"{item['emotion']}|{','.join(map(str, item['tags'][:5]))}"
                        for item in candidates
                    ],
                ]
            )
            response = await self._generate(
                event,
                prompt,
                image_urls=[],
                provider_id=configured_provider_id(
                    self.config,
                    "reply_scene_provider_id",
                    "scene_provider_id",
                ),
                system_prompt=OUTGOING_DECISION_COMPACT_PROMPT,
            )
            choice = parse_model_json(response)
            should_send = self._model_bool(choice.get("should_send"), default=False)
            reason = str(choice.get("reason", "") or "")[:80]
            confidence = choice.get("confidence", "")
            if not should_send:
                logger.info(
                    "[meme_manager_master] 情景分析决定不发送 confidence=%s reason=%s",
                    confidence,
                    reason,
                )
                return None
            candidate_id = str(choice.get("candidate_id", "")).strip()
            for item in candidates:
                if candidate_id in {item["id"], item["filename"]}:
                    details = self._image_details(item["path"])
                    logger.info(
                        "[meme_manager_master] 情景分析决定发送 category=%s candidate=%s "
                        "confidence=%s reason=%s description=%s",
                        details["category"],
                        candidate_id,
                        confidence,
                        reason,
                        details["description"],
                    )
                    return item["path"]
            logger.warning(
                "[meme_manager_master] 情景分析选择了不存在的候选 candidate=%s reason=%s",
                candidate_id,
                reason,
            )
        except Exception as exc:
            logger.warning("[meme_manager_master] 单次智能回复决策失败，不发送表情包: %s", exc)
        return None

    def _image_details(self, path: Path) -> dict[str, object]:
        category = path.parent.name
        catalog = self.store.load_catalog(category)
        entry = next(
            (
                item
                for item in catalog.get("items", [])
                if isinstance(item, dict) and item.get("filename") == path.name
            ),
            {},
        )
        tags = entry.get("tags", []) if isinstance(entry, dict) else []
        if not isinstance(tags, list):
            tags = [tags]
        return {
            "category": category,
            "filename": path.name,
            "description": str(entry.get("description", "") or "")[:120],
            "emotion": str(entry.get("emotion", "") or "")[:40],
            "text": str(entry.get("text", "") or "")[:120],
            "tags": [str(tag)[:30] for tag in tags[:5]],
        }

    @staticmethod
    def _catalog_entry_from_vision(path: Path, category: str, vision: dict, scene: dict) -> dict:
        tags = vision.get("tags", [])
        if isinstance(tags, str):
            tags = [item.strip() for item in re.split(r"[,，、]", tags) if item.strip()]
        if not isinstance(tags, list):
            tags = []
        return {
            "id": path.stem,
            "filename": path.name,
            "category": category,
            "description": str(vision.get("description", "") or "")[:120],
            "emotion": str(vision.get("emotion", scene.get("category", "")) or "")[:40],
            "text": str(vision.get("text", "") or "")[:120],
            "tags": [str(item)[:30] for item in tags[:8] if str(item).strip()],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "indexed": False,
            "index_source": "capture",
            "captured_at": int(time.time()),
        }

    @staticmethod
    def _library_index_metadata(provider_id: str) -> dict:
        return {
            "index_version": LIBRARY_INDEX_VERSION,
            "index_prompt_version": LIBRARY_INDEX_PROMPT_VERSION,
            "index_provider_id": provider_id,
            "classification_index_complete": True,
        }

    @staticmethod
    def _catalog_entry_is_current(entry: dict | None, provider_id: str) -> bool:
        if not isinstance(entry, dict) or not entry.get("indexed", False):
            return False
        metadata = CaptureMixin._library_index_metadata(provider_id)
        return index_metadata_matches(entry, metadata)

    def _perceptual_duplicate_threshold(self) -> int | None:
        if not self._bool_config("perceptual_dedupe_enabled", True):
            return None
        return self._int_config("perceptual_duplicate_threshold", 6, 0, 16)

    @staticmethod
    def _progress_text(processed: int, total: int, errors: int) -> str:
        ratio = processed / max(total, 1)
        width = 20
        filled = int(ratio * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"整理进度 [{bar}] {ratio:.0%}（{processed}/{total}，失败 {errors}）"

    async def _recognize_image(
        self,
        event: AstrMessageEvent,
        image_path: Path,
        message_text: str,
    ) -> dict:
        prompt = (
            "请识别这张群聊图片。图片来自以下消息语境，仅作辅助，不要把消息文字当作图片文字：\n"
            f"{message_text[:500]}"
        )
        try:
            response_text = await self._generate(
                event,
                prompt,
                image_urls=[str(image_path)],
                provider_id=configured_provider_id(self.config, "vision_provider_id"),
                system_prompt=VISION_SYSTEM_PROMPT,
            )
            return parse_model_json(response_text)
        except Exception as exc:
            logger.warning("[meme_manager_master] 视觉模型失败，拒绝保存图片: %s", exc)
            return vision_failure_result()

    async def _classify_scene(
        self,
        event: AstrMessageEvent,
        vision: dict,
        categories: set[str],
        message_text: str,
        message_outline: str,
    ) -> dict:
        prompt = (
            f"图片识别结果：{vision}\n"
            f"当前消息文字：{message_text[:500]}\n"
            f"消息概要：{message_outline[:500]}"
        )
        try:
            response_text = await self._generate(
                event,
                prompt,
                image_urls=[],
                provider_id=configured_provider_id(self.config, "scene_provider_id"),
                system_prompt=_scene_system_prompt(categories),
            )
            return parse_model_json(response_text)
        except Exception as exc:
            logger.warning("[meme_manager_master] 情景模型失败，将使用 fallback_category: %s", exc)
            return {}

    @staticmethod
    def _model_bool(value, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "是", "发送"}
        return bool(value)

    def _is_control_command(self, event: AstrMessageEvent) -> bool:
        text = self._event_text(event)
        return bool(re.match(r"^\s*(?:[/!#])?(?:偷取|表情偷取状态)(?:\s|$)", text))

    async def _generate(
        self,
        event: AstrMessageEvent | None,
        prompt: str,
        image_urls: list[str],
        provider_id: str,
        system_prompt: str,
    ) -> str:
        if not provider_id:
            provider_id = await self._current_provider_id(event)
        if not provider_id or not hasattr(self.context, "llm_generate"):
            raise RuntimeError("没有可用的 AstrBot LLM Provider，请配置 provider_id")
        response = await self.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=prompt,
            image_urls=image_urls,
            system_prompt=system_prompt,
            contexts=[],
        )
        text = getattr(response, "completion_text", "")
        if text:
            return str(text)
        chain = getattr(response, "result_chain", None)
        if chain:
            return "".join(str(getattr(item, "text", "")) for item in chain)
        raise RuntimeError("LLM 返回为空")

    async def _current_provider_id(self, event: AstrMessageEvent | None) -> str:
        if event is None:
            return ""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        getter = getattr(self.context, "get_current_chat_provider_id", None)
        if not callable(getter):
            return ""
        try:
            return str(await getter(umo=umo) or "").strip()
        except TypeError:
            return str(await getter(umo) or "").strip()

    async def _load_image(self, source: str) -> ImagePayload | None:
        limit = self._int_config("max_image_size_mb", 10, 1, 50) * 1024 * 1024
        if source.startswith("data:"):
            return self._decode_data_url(source, limit)
        if source.startswith("base64://"):
            return self._decode_base64(source[9:], limit)
        if source.startswith(("http://", "https://")):
            return await self._download_image(source, limit)
        if source.startswith("file://"):
            source = unquote(urlparse(source).path)
        path = Path(source)
        if not self._is_allowed_local_image_path(path):
            logger.warning("[meme_manager_master] 拒绝读取不在允许目录内的本地图片: %s", source)
            return None
        if not path.is_file():
            logger.debug("[meme_manager_master] 图片来源不存在: %s", source)
            return None
        content = path.read_bytes()
        if len(content) > limit:
            logger.warning("[meme_manager_master] 图片超过大小限制: %s", path)
            return None
        payload = self._payload_from_content(content, limit)
        if payload is None:
            logger.warning("[meme_manager_master] local file is not a valid image: %s", path)
        return payload

    def _is_allowed_local_image_path(self, path: Path) -> bool:
        """Restrict local image reads to AstrBot data/temp roots or configured roots."""
        if not path.is_absolute():
            return False
        configured = self.config.get("local_image_roots", [])
        if isinstance(configured, str):
            configured = re.split(r"[,\n]", configured)
        elif not isinstance(configured, (list, tuple)):
            configured = []
        roots = [self.store.root, Path(tempfile.gettempdir())]
        try:
            roots.append(self.store.root.parents[1])
        except IndexError:
            pass
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            astrbot_data_root = Path(get_astrbot_data_path()).resolve()
            roots.extend((astrbot_data_root, astrbot_data_root / "temp"))
        except (ImportError, OSError, TypeError):
            # AstrBot is optional in the offline test environment.
            pass
        roots.extend(Path(str(item)) for item in configured or [] if str(item).strip())
        try:
            candidate = path.resolve(strict=False)
            resolved_roots = [root.resolve(strict=False) for root in roots]
        except OSError:
            return False
        return any(candidate == root or root in candidate.parents for root in resolved_roots)

    async def _remote_target_is_public(self, source: str) -> bool:
        """Resolve a remote image host and reject private, local, or unroutable IPs."""
        if not is_safe_remote_image_url(source):
            return False
        parsed = urlparse(source)
        hostname = parsed.hostname
        if not hostname:
            return False
        try:
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except (OSError, ValueError):
            return False
        resolved = {
            str(info[4][0]).split("%", 1)[0]
            for info in addresses
            if info and len(info) > 4 and info[4]
        }
        if not resolved:
            return False
        try:
            return all(ip_address(address).is_global for address in resolved)
        except ValueError:
            return False

    async def _download_image(self, source: str, limit: int) -> ImagePayload | None:
        if not await self._remote_target_is_public(source):
            logger.warning("[meme_manager_master] 拒绝访问不安全的远程图片地址: %s", source)
            return None
        timeout = aiohttp.ClientTimeout(total=self._float_config("download_timeout", 20, 5, 120))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(source, allow_redirects=False) as response:
                    response.raise_for_status()
                    content_length = int(response.headers.get("Content-Length", "0") or 0)
                    if content_length > limit:
                        logger.warning("[meme_manager_master] 远程图片超过大小限制: %s", source)
                        return None
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        total += len(chunk)
                        if total > limit:
                            logger.warning("[meme_manager_master] 远程图片超过大小限制: %s", source)
                            return None
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    payload = self._payload_from_content(content, limit)
                    if payload is None:
                        logger.warning(
                            "[meme_manager_master] downloaded content is not a valid image: %s content_type=%s",
                            source,
                            response.headers.get("Content-Type", ""),
                        )
                    return payload
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.warning("[meme_manager_master] 下载图片失败 %s: %s", source, exc)
            return None

    @staticmethod
    def _decode_data_url(source: str, limit: int) -> ImagePayload | None:
        match = re.match(r"data:image/([a-zA-Z0-9.+-]+);base64,(.+)", source, re.DOTALL)
        if not match:
            return None
        return CaptureMixin._decode_base64(match.group(2), limit)

    @staticmethod
    def _decode_base64(value: str, limit: int) -> ImagePayload | None:
        try:
            content = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            return None
        return CaptureMixin._payload_from_content(content, limit)

    @staticmethod
    def _payload_from_content(content: bytes, limit: int) -> ImagePayload | None:
        if not content or len(content) > limit:
            return None
        extension = detect_image_extension(content)
        if extension is None:
            return None
        return ImagePayload(content, extension)

    def _should_skip(self, vision: dict) -> bool:
        if not self._bool_config("only_capture_memes", True):
            return False
        rejection_confidence = self._float_config(
            "meme_rejection_confidence", 0.7, 0, 1
        )
        return should_skip_meme_result(vision, rejection_confidence)

    @staticmethod
    def _event_text(event: AstrMessageEvent) -> str:
        getter = getattr(event, "get_message_str", None)
        if callable(getter):
            return str(getter() or "")
        return str(getattr(event, "message_str", "") or "")

    @staticmethod
    def _event_outline(event: AstrMessageEvent) -> str:
        getter = getattr(event, "get_message_outline", None)
        if callable(getter):
            try:
                return str(getter() or "")
            except Exception:
                pass
        return CaptureMixin._event_text(event)

    def _whitelist(self) -> list[str]:
        value = self.config.get("group_whitelist", [])
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[,\n]", value) if item.strip()]
        return [str(item).strip() for item in value or [] if str(item).strip()]

    def _bool_config(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return bool(value)

    def _float_config(self, key: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(self.config.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _int_config(self, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(self.config.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _log_task_failure(task: asyncio.Task) -> None:
        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return
        if exception:
            logger.error("[meme_manager_master] 后台任务异常: %s", exception)

    async def terminate(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
            await asyncio.gather(self._health_task, return_exceptions=True)
        if self._library_task is not None:
            self._library_task.cancel()
            await asyncio.gather(self._library_task, return_exceptions=True)
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
