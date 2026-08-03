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
    contains_meme_send_claim,
    configured_provider_id,
    drop_empty_text_components,
    event_identity,
    explicit_meme_request,
    extract_meme_markers,
    extract_image_sources,
    filter_reply_hook_available,
    group_id_from_event,
    is_meme_follow_up_request,
    is_safe_remote_image_url,
    parse_model_json,
    should_block_agent_tool_for_meme_request,
    should_skip_meme_result,
    strip_meme_markers,
    vision_failure_result,
    wait_for_filter_reply_lock,
    whitelist_allows,
)
from .meme_selection import MemeSelectionService
from .capture_pipeline import CapturePipeline
from .capture_activity import (
    index_metadata_matches,
    mark_capture_events_indexed,
    record_capture_event,
)
from .health import MemeManagerHealth, check_meme_manager_master_health
from .indexing import catalog_needs_write, normalize_library_results
from .response_policy import success_reply_text
from .runtime_config import PluginConfig, consume_migration_used
from .storage import MemeStore, detect_image_extension
from .backend.tagging import normalize_tags


VISION_SYSTEM_PROMPT = """
你是一个负责识别聊天表情包的视觉模型。请只输出 JSON，不要 Markdown，不要解释。
判断图片是否像聊天表情包：包含明显情绪、反应、吐槽、文字梗或用于表达态度的画面。
JSON 格式：
{"is_meme": true, "confidence": 0.0, "description": "简短中文描述", "emotion": "情绪", "text": "图片中的文字"}
""".strip()


def _library_batch_system_prompt(category: str) -> str:
    return f"""
你是表情包素材库批量整理器。当前收到多张图片，请根据画面含义为每张图片选择固定标签。
可选标签必须来自：开心、愤怒、悲伤、震惊、疑惑、尴尬、害怕、期待、无语、赞同、拒绝、嘲讽、嫌弃、感谢、道歉、安慰、催促、围观、吃瓜、摸鱼、庆祝、工作、加班、睡觉、早安、求助、发钱、其他。每张最多选择5个标签。
不要创建新标签，也不要移动图片。请为每张图片输出一条结果，并严格保留输入的 id。
只输出 JSON，不要 Markdown。
格式：{{"items":[{{"id":"image_0", "description":"不超过40字", "emotion":"主要情绪", "text":"图片文字，没有则为空", "tags":["关键词1"]}}]}}
""".strip()


def _library_single_system_prompt(category: str) -> str:
    return f"""
你是表情包素材库单图整理器。请根据画面含义从固定标签中选择最多5个标签，不要创建新标签，也不要移动图片。
固定标签：开心、愤怒、悲伤、震惊、疑惑、尴尬、害怕、期待、无语、赞同、拒绝、嘲讽、嫌弃、感谢、道歉、安慰、催促、围观、吃瓜、摸鱼、庆祝、工作、加班、睡觉、早安、求助、发钱、其他。
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
        self.config_raw = self.config
        self.runtime_config = PluginConfig.from_mapping(self.config)
        self.store = MemeStore.from_astrbot()
        self._semaphore = asyncio.Semaphore(self.runtime_config.max_concurrent)
        self._save_lock = asyncio.Lock()
        self.capture_pipeline = CapturePipeline(
            store=self.store,
            config=self.runtime_config,
            semaphore=self._semaphore,
            save_lock=self._save_lock,
            generate=self._generate,
            activity_recorder=record_capture_event,
            loader=self._load_image,
            recognize_single=self._recognize_image,
            classify_single=self._classify_scene,
            should_skip=self._should_skip,
            catalog_entry_builder=CaptureMixin._catalog_entry_from_vision,
            bind_saved_result=self._bind_saved_image,
        )
        self.meme_selection = MemeSelectionService(
            store=self.store,
            config=self.runtime_config,
            generate=self._generate,
            event_text=self._event_text,
            image_details=self._image_details,
            model_bool=self._model_bool,
        )
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
        self._forced_meme_results: dict[str, tuple[float, Path, dict]] = {}

    async def initialize(self) -> None:
        """Check the required plugin before accepting any image."""
        await self._refresh_health(force=True)
        self._health_task = asyncio.create_task(self._health_loop())

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(self.runtime_config.health_check_interval)
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
        interval = self.runtime_config.health_check_interval
        if store_changed or time.monotonic() - self._last_health_check >= interval:
            await self._refresh_health(force=store_changed)
        return self._health.ready

    def _recent_meme_sent(self, event: AstrMessageEvent) -> bool:
        """Return whether this chat recently received a meme from this plugin."""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        sent_at = self._last_auto_send.get(umo, 0.0)
        if not umo or not sent_at:
            return False
        window = self.runtime_config.meme_follow_up_window
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
        window = self.runtime_config.meme_follow_up_window
        if time.monotonic() - requested_at > window:
            self._explicit_meme_requests.pop(umo, None)
            return False
        return True

    def _clear_explicit_request(self, event: AstrMessageEvent) -> None:
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if umo:
            self._explicit_meme_requests.pop(umo, None)

    def _remember_forced_meme_result(
        self,
        event: AstrMessageEvent,
        image_path: Path,
        details: dict,
    ) -> None:
        """Keep an explicit-send result until the final response stage."""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if not umo or not image_path.is_file():
            return
        self._forced_meme_results[umo] = (time.monotonic(), image_path, dict(details))

    @staticmethod
    def _explicit_success_chain(image_path: Path, existing_text: str = "") -> list:
        chain = []
        visible_text = success_reply_text(existing_text)
        if visible_text:
            chain.append(Comp.Plain(visible_text))
        chain.append(Comp.Image.fromFileSystem(str(image_path)))
        return chain

    def _restore_forced_meme_result(self, event: AstrMessageEvent) -> bool:
        """Restore a local meme if an Agent continuation overwrote event.result."""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        entry = self._forced_meme_results.get(umo)
        result = event.get_result()
        if not umo or entry is None or result is None:
            return False
        sent_at, image_path, _details = entry
        window = self.runtime_config.meme_follow_up_window
        if time.monotonic() - sent_at > window or not image_path.is_file():
            self._forced_meme_results.pop(umo, None)
            return False
        result.chain = self._explicit_success_chain(image_path)
        self._forced_meme_results.pop(umo, None)
        logger.info(
            "[meme_manager_master] restored explicit meme result before final send file=%s",
            image_path,
        )
        return True

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

    async def _record_image_send(self, image_path: Path) -> None:
        """Persist the successful-send marker without racing catalog writes."""
        async with self._save_lock:
            self.store.mark_image_sent(image_path)

    @staticmethod
    def _queue_send_weight_mark(event: AstrMessageEvent, image_path: Path) -> None:
        event.set_extra("meme_manager_master_send_mark_path", str(image_path))

    def _send_receipt_for_event(self, event: AstrMessageEvent) -> dict | None:
        """Return the current event's real meme-send receipt, if one exists."""
        key = event_identity(event)
        entry = self._meme_send_receipts.get(key)
        if entry is None:
            return None
        sent_at, _image_path, details = entry
        window = self.runtime_config.meme_follow_up_window
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
        window = self.runtime_config.meme_follow_up_window
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
                explicit_handled = bool(
                    getattr(event, "_meme_manager_master_explicit_handled", False)
                )
                if not force or explicit_handled:
                    logger.debug(
                        "[meme_manager_master] 跳过同一事件的重复表情包发送 event=%s",
                        key,
                    )
                    return False
                # AstrBot may reuse an event identity for a new direct request
                # captured as an Agent follow-up. A forced request is allowed
                # to claim that reused identity again.
                self._auto_send_claims.pop(key, None)
                logger.debug(
                    "[meme_manager_master] 允许新的显式表情包请求复用事件标识 event=%s",
                    key,
                )
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            cooldown = self.runtime_config.auto_send_cooldown
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
        """Remove only an unverified send claim while preserving the reply body."""
        if self._send_receipt_for_event(event) is not None:
            return
        changed = False
        for component in chain:
            if not hasattr(component, "text"):
                continue
            text = str(getattr(component, "text", "") or "")
            if not contains_meme_send_claim(text):
                continue
            parts = re.split(r"([，,。！？!?；;\n])", text)
            segments: list[str] = []
            current = ""
            for part in parts:
                current += part
                if re.fullmatch(r"[，,。！？!?；;\n]", part):
                    segments.append(current)
                    current = ""
            if current:
                segments.append(current)
            cleaned = "".join(
                segment
                for segment in segments
                if not contains_meme_send_claim(segment)
            ).strip()
            cleaned = re.sub(r"^[，,；;：:]|[，,；;：:]$", "", cleaned).strip()
            component.text = cleaned
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
        event.stop_event()

    async def _handle_explicit_meme_request(
        self,
        event: AstrMessageEvent,
        message_text: str,
    ) -> None:
        """Handle a direct meme request before the default Agent can use tools."""
        self._clear_explicit_request(event)
        if not await self._manager_ready():
            setattr(event, "_meme_manager_master_explicit_handled", True)
            event.set_result(
                event.plain_result("本地表情包管理器当前不可用，暂时无法发送表情包。")
            )
            self._disable_default_llm(event)
            return
        if not await self._claim_auto_send(event, force=True):
            self._disable_default_llm(event)
            return
        setattr(event, "_meme_manager_master_explicit_handled", True)

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

        details = self._image_details(image_path)
        self._remember_forced_meme_result(event, image_path, details)
        self._queue_send_weight_mark(event, image_path)
        event.set_result(event.chain_result(self._explicit_success_chain(image_path)))
        self._disable_default_llm(event)
        logger.info(
            "[meme_manager_master] explicit meme request handled before default Agent file=%s",
            image_path,
        )

    def _schedule_library_index(self) -> None:
        """Schedule an idempotent scan when meme_manager_master is healthy."""
        if not self.runtime_config.library_index_enabled:
            return
        provider_id = configured_provider_id(
            self.runtime_config,
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
        self.store.reindex_flat_catalog()
        signature = []
        for path in self.store.image_paths():
            try:
                signature.append((path.name, self.store.image_digest(path)))
            except OSError:
                continue
        return tuple(signature)
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
        catalog = self.store.load_catalog()
        if not source_signature or not catalog.get("classification_index_complete"):
            return False
        expected = self._library_index_metadata(provider_id)
        if not index_metadata_matches(catalog, expected):
            return False
        if catalog.get("classification_index_file_total") != len(source_signature):
            return False
        by_digest = {
            str(item.get("sha256")): item
            for item in catalog.get("items", [])
            if isinstance(item, dict) and item.get("sha256")
        }
        return all(
            self._catalog_entry_is_current(by_digest.get(digest), provider_id)
            for _filename, digest in source_signature
        )
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
            self.runtime_config.health_check_interval,
            60,
        )

    def _log_library_task_failure(self, task: asyncio.Task) -> None:
        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return
        if exception:
            self._library_index_state.update(
                status="error",
                message=f"标签索引失败：{exception}",
            )
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
        message_text = self._event_text(event)
        if explicit_meme_request(message_text):
            # A follow-up request may reuse the same AstrBot event object.
            setattr(event, "_meme_manager_master_explicit_handled", False)
        self._remember_explicit_request(event)
        if getattr(event, "_meme_manager_master_manual", False):
            return
        if not self.runtime_config.enabled:
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
        limit = self.runtime_config.max_images_per_message
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

        limit = self.runtime_config.max_images_per_message
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
        if not self.runtime_config.proactive_send_after_steal:
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
            await self._record_image_send(image_path)
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
        self._queue_send_weight_mark(event, image_path)
        yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])

    async def after_message_sent(self, event: AstrMessageEvent) -> None:
        """Send a selected automatic meme only after the reply was delivered."""
        path_value = event.get_extra("meme_manager_master_auto_send_path")
        details = event.get_extra("meme_manager_master_auto_send_details")
        mark_value = event.get_extra("meme_manager_master_send_mark_path")
        event.set_extra("meme_manager_master_auto_send_path", None)
        event.set_extra("meme_manager_master_auto_send_details", None)
        event.set_extra("meme_manager_master_send_mark_path", None)

        auto_path = Path(str(path_value)) if path_value else None
        mark_path = Path(str(mark_value)) if mark_value else None
        if auto_path is not None:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            if umo and auto_path.is_file():
                try:
                    filter_wait_state = await wait_for_filter_reply_lock(event)
                    if filter_wait_state == "timeout":
                        logger.warning(
                            "[meme_manager_master] 等待 Filter 文本分段完成超时，继续发送自动表情包"
                        )
                    elif filter_wait_state == "released":
                        logger.info(
                            "[meme_manager_master] Filter 文本分段已全部发送，继续发送自动表情包"
                        )
                    message_chain = MessageChain().file_image(str(auto_path))
                    await self.context.send_message(umo, message_chain)
                    await self._record_image_send(auto_path)
                    if not isinstance(details, dict):
                        details = self._image_details(auto_path)
                    self._last_auto_send[umo] = time.monotonic()
                    self._remember_sent_meme(event, auto_path, details)
                    self._arm_agent_tool_guard(event)
                    logger.info(
                        "[meme_manager_master] 正文发送完成后发送自动表情包 path=%s",
                        auto_path,
                    )
                except Exception as exc:
                    logger.warning(
                        "[meme_manager_master] 正文发送完成后发送自动表情包失败: %s",
                        exc,
                        exc_info=True,
                    )
            if mark_path == auto_path:
                mark_path = None
        if mark_path is not None and mark_path.is_file():
            await self._record_image_send(mark_path)
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            if umo:
                self._last_auto_send[umo] = time.monotonic()
            self._remember_sent_meme(event, mark_path)
            self._arm_agent_tool_guard(event)

    async def status(self, event: AstrMessageEvent):
        """显示 meme_manager_master 依赖插件的加载与数据目录状态。"""
        health = await self._refresh_health(force=True)
        yield event.plain_result(health.summary())

    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        """Replace meme_manager_master's marker sender with this plugin's sender."""
        result = event.get_result()
        if result and self._restore_forced_meme_result(event):
            return
        if getattr(event, "_meme_manager_master_explicit_handled", False):
            return
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
            not self.runtime_config.auto_send_enabled
            or (not plain_texts and not marked_categories and not force_send)
            or self._is_control_command(event)
            or not await self._manager_ready()
        ):
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
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        cooldown = self.runtime_config.auto_send_cooldown
        if (
            cooldown
            and not force_send
            and time.monotonic() - self._last_auto_send.get(umo, 0) < cooldown
        ):
            self._rewrite_unverified_meme_claim(event, chain)
            return

        probability = self.runtime_config.auto_send_probability
        if not force_send and (probability <= 0 or random.random() * 100 >= probability):
            self._rewrite_unverified_meme_claim(event, chain)
            return
        if not await self._claim_auto_send(event, force=force_send):
            self._rewrite_unverified_meme_claim(event, chain)
            return

        details = self._image_details(image_path)
        result.chain = drop_empty_text_components(chain)
        if not plain_texts or not filter_reply_hook_available(event):
            # A marker-only or otherwise textless result may never trigger
            # after_message_sent. Likewise, without Filter's reply hook there
            # is nobody to wait for. Put the selected image into the current
            # result so AstrBot can deliver it without a follow-up hook.
            result.chain.append(Comp.Image.fromFileSystem(str(image_path)))
            self._queue_send_weight_mark(event, image_path)
            logger.info(
                "[meme_manager_master] 无 Filter 回复钩子或无可见正文，直接加入当前消息链发送自动表情包 path=%s",
                image_path,
            )
            return
        event.set_extra("meme_manager_master_auto_send_path", str(image_path))
        event.set_extra("meme_manager_master_auto_send_details", details)
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

    @staticmethod
    def _remove_retired_agent_tools(req) -> None:
        """Remove semantic tools left behind by an older loaded plugin copy."""
        tool_set = getattr(req, "func_tool", None)
        if tool_set is None:
            return
        get_full_tool_set = getattr(tool_set, "get_full_tool_set", None)
        if callable(get_full_tool_set):
            req.func_tool = get_full_tool_set()
            tool_set = req.func_tool
        remove_tool = getattr(tool_set, "remove_tool", None)
        if callable(remove_tool):
            remove_tool("search_memes")
            return
        if isinstance(tool_set, dict):
            tool_set.pop("search_memes", None)
            return
        tools = getattr(tool_set, "tools", None)
        if isinstance(tools, list):
            tool_set.tools = [
                tool
                for tool in tools
                if (
                    getattr(tool, "name", "")
                    or (tool.get("name", "") if isinstance(tool, dict) else "")
                )
                != "search_memes"
            ]

    async def on_llm_request(self, event: AstrMessageEvent, req) -> None:
        """Inject recent meme context and remove image-producing Agent tools."""
        self._remember_explicit_request(event)
        message_text = self._event_text(event)
        self._remove_retired_agent_tools(req)
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
        if tool_name == "search_memes":
            self._disable_default_llm(event)
            event.stop_event()
            logger.warning(
                "[meme_manager_master] blocked retired Agent tool: %s",
                tool_name,
            )
            return
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
        return await self.capture_pipeline.process_one(
            event, source, message_text, message_outline
        )

    async def _process_batch(
        self,
        event: AstrMessageEvent,
        sources: list[str],
        message_text: str,
        message_outline: str,
    ) -> list[str]:
        return await self.capture_pipeline.process_batch(
            event, sources, message_text, message_outline
        )

    async def _ensure_flat_library_index(self) -> None:
        """Classify pending flat memes and rebuild the unified tag index."""
        if self._library_lock.locked():
            return
        async with self._library_lock:
            self.store.reindex_flat_catalog()
            catalog = self.store.load_catalog()
            items = [item for item in catalog.get("items", []) if isinstance(item, dict)]
            paths = {
                item["filename"]: self.store.memes_dir / item["filename"]
                for item in items
                if isinstance(item.get("filename"), str)
                and (self.store.memes_dir / item["filename"]).is_file()
            }
            total = len(paths)
            self._library_index_state.update(
                status="running",
                processed=0,
                total=total,
                classified=0,
                errors=0,
                message="正在检查标签索引……",
            )
            if not total:
                self._library_index_state.update(status="idle", message="没有待索引图片")
                return
            provider_id = configured_provider_id(
                self.runtime_config,
                "library_index_provider_id",
                "vision_provider_id",
            )
            if not provider_id:
                self._library_index_state.update(
                    status="blocked", message="未配置标签索引视觉模型"
                )
                return

            run_signature = self._library_source_signature()
            by_filename = {item["filename"]: item for item in items if item.get("filename")}
            index_metadata = self._library_index_metadata(provider_id)
            records: dict[str, dict] = {}
            pending: list[tuple[Path, str]] = []
            catalog_is_current = index_metadata_matches(catalog, index_metadata)
            for filename, path in paths.items():
                digest = self.store.image_digest(path)
                old_entry = by_filename.get(filename)
                if (
                    catalog_is_current
                    and old_entry
                    and old_entry.get("sha256") == digest
                    and self._catalog_entry_is_current(old_entry, provider_id)
                ):
                    records[filename] = dict(old_entry)
                else:
                    pending.append((path, digest))

            processed = len(records)
            classified = 0
            errors = 0
            batch_size = self.runtime_config.library_index_batch_size
            for start in range(0, len(pending), batch_size):
                batch = pending[start : start + batch_size]
                batch_paths = [path for path, _digest in batch]
                classified += len(batch)
                try:
                    batch_results = await self._describe_library_batch(
                        None, batch_paths, "固定标签", provider_id
                    )
                except Exception as exc:
                    logger.debug(
                        "标签索引批次失败，改用逐图识别 count=%s: %s",
                        len(batch),
                        exc,
                    )
                    batch_results = {}
                    for path in batch_paths:
                        try:
                            batch_results.update(
                                await self._describe_library_single(
                                    None, path, "固定标签", provider_id
                                )
                            )
                        except Exception as single_exc:
                            logger.debug("single-image tag index failed path=%s: %s", path, single_exc)
                    if not batch_results:
                        self._schedule_library_retry(provider_id)
                        self._library_index_state.update(
                            status="completed_with_errors",
                            processed=processed,
                            classified=classified,
                            errors=errors + len(batch),
                            message="标签索引失败，稍后可重试",
                        )
                        return
                for path, digest in batch:
                    metadata = dict(batch_results.get(path) or {})
                    if not metadata:
                        errors += 1
                        metadata = {"description": "待重新识别", "emotion": "未知", "text": "", "tags": [], "indexed": False}
                    previous = by_filename.get(path.name)
                    if isinstance(previous, dict):
                        for key in ("send_count", "last_sent_at"):
                            if key in previous:
                                metadata[key] = previous[key]
                        metadata["tags"] = [*(previous.get("tags") or []), *(metadata.get("tags") or [])]
                    metadata.update({
                        "id": path.stem,
                        "filename": path.name,
                        "sha256": digest,
                        "tags": normalize_tags(metadata.get("tags")),
                        "perceptual_hash": self.store.image_perceptual_hash(path),
                        **index_metadata,
                    })
                    records[path.name] = metadata
                    processed += 1

            async with self._save_lock:
                if self._library_source_signature() != run_signature:
                    self._schedule_library_retry(provider_id)
                    self._library_index_state.update(status="completed_with_errors", errors=errors + 1)
                    return
                entries = [records[name] for name in sorted(paths) if name in records]
                complete = len(entries) == total and all(bool(item.get("indexed")) for item in entries)
                index_metadata = {
                    **index_metadata,
                    "classification_index_complete": complete,
                    "classification_indexed_at": int(time.time()),
                    "classification_index_file_total": len(entries),
                }
                if catalog_needs_write(catalog, entries, index_metadata):
                    self.store.write_catalog(entries, index_metadata)
                for tag in {tag for item in entries for tag in item.get("tags", [])}:
                    mark_capture_events_indexed(
                        self.store.root,
                        category=tag,
                        digests={str(item.get("sha256")) for item in entries if tag in item.get("tags", [])},
                    )
            self._library_index_state.update(
                status="completed" if not errors else "completed_with_errors",
                processed=processed,
                classified=classified,
                errors=errors,
                message="标签索引完成" if not errors else "标签索引完成，但有图片待重试",
            )
            self._library_completed_key = (provider_id, run_signature)
            self._library_retry_key = None
            self._library_retry_at = 0.0

    async def _ensure_library_index(self) -> None:
        return await self._ensure_flat_library_index()

    async def _ensure_legacy_library_index(self) -> None:
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
                self.runtime_config,
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
            progress_step = self.runtime_config.library_index_progress_step
            for category in categories:
                paths = self.store.image_paths(category)
                old_catalog = self.store.load_catalog(category)
                by_digest = {
                    str(item.get("sha256")): item
                    for item in old_catalog.get("items", [])
                    if isinstance(item, dict) and item.get("sha256")
                }
                by_filename = {
                    str(item.get("filename")): item
                    for item in old_catalog.get("items", [])
                    if isinstance(item, dict) and item.get("filename")
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

                batch_size = self.runtime_config.library_index_batch_size
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
                        previous = by_filename.get(path.name)
                        if isinstance(previous, dict):
                            for key in ("send_count", "last_sent_at"):
                                if key in previous:
                                    metadata[key] = previous[key]
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
                        if self.runtime_config.library_index_rename_files
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
        return await self.meme_selection.choose(
            event,
            response_text,
            force_send=force_send,
            preferred_categories=preferred_categories,
        )

    async def _choose_outgoing_meme_legacy(
        self,
        event: AstrMessageEvent,
        response_text: str,
        force_send: bool = False,
        preferred_categories: list[str] | None = None,
    ) -> Path | None:
        return await self.meme_selection.choose_legacy(
            event,
            response_text,
            force_send=force_send,
            preferred_categories=preferred_categories,
        )

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
        if not self.runtime_config.perceptual_dedupe_enabled:
            return None
        return self.runtime_config.perceptual_duplicate_threshold

    @staticmethod
    def _progress_text(processed: int, total: int, errors: int) -> str:
        ratio = processed / max(total, 1)
        width = 20
        filled = int(ratio * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"整理进度 [{bar}] {ratio:.0%}（{processed}/{total}，失败 {errors}）"

    def _bind_saved_image(self, event: AstrMessageEvent, path: Path) -> None:
        """Record a saved/duplicate image against the current session."""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if umo:
            self._last_stolen_image[umo] = path
        self._stolen_image_by_event[event_identity(event)] = path

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
                provider_id=configured_provider_id(self.runtime_config, "vision_provider_id"),
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
                provider_id=configured_provider_id(self.runtime_config, "scene_provider_id"),
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
        limit = self.runtime_config.max_image_size_mb * 1024 * 1024
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
        configured = self.runtime_config.local_image_roots
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
        timeout = aiohttp.ClientTimeout(total=self.runtime_config.download_timeout)
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
        if not self.runtime_config.only_capture_memes:
            return False
        rejection_confidence = self.runtime_config.meme_rejection_confidence
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
        value = self.runtime_config.group_whitelist
        return [str(item).strip() for item in value or [] if str(item).strip()]

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
