"""Collect group images, classify them, and store them for meme_manager."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiohttp
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.star import Context, Star, register

from .collector import (
    configured_provider_id,
    event_identity,
    explicit_meme_request,
    extract_meme_markers,
    extract_image_sources,
    group_id_from_event,
    normalize_category,
    parse_model_json,
    stop_event_propagation,
    strip_meme_markers,
    whitelist_allows,
)
from .health import MemeManagerHealth, check_meme_manager_health
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
你是表情包素材库批量整理器。当前收到多张图片，它们都已经位于 meme_manager 的 {category} 分类目录。
目录名是权威分类，不要移动或重新分类图片。请为每张图片输出一条结果，并严格保留输入的 id。
只输出 JSON，不要 Markdown。
格式：{{"items":[{{"id":"image_0", "description":"不超过40字", "emotion":"主要情绪", "text":"图片文字，没有则为空", "tags":["关键词1"]}}]}}
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


LIBRARY_INDEX_VERSION = 2
LIBRARY_INDEX_PROMPT_VERSION = "library-batch-v2"


@dataclass(frozen=True)
class ImagePayload:
    content: bytes
    extension: str


@register(
    "meme_stealer",
    "YourName",
    "自动识别并收集群聊表情包到 meme_manager",
    "1.4.0",
)
class MemeStealer(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.store = MemeStore.from_astrbot()
        self._semaphore = asyncio.Semaphore(self._int_config("max_concurrent", 2, 1, 8))
        self._save_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._health = MemeManagerHealth(
            status="plugin_missing",
            reason="尚未完成 meme_manager 健康检查。",
            data_root=self.store.root,
        )
        self._last_health_check = 0.0
        self._health_task: asyncio.Task | None = None
        self._library_task: asyncio.Task | None = None
        self._library_lock = asyncio.Lock()
        self._last_auto_send: dict[str, float] = {}
        self._auto_send_claims: dict[str, float] = {}
        self._auto_send_claim_lock = asyncio.Lock()
        self._pending_auto_images: dict[str, tuple[str, Path]] = {}
        self._last_stolen_image: dict[str, Path] = {}

    async def initialize(self) -> None:
        """Check the required plugin before accepting any image."""
        await self._refresh_health(force=True)
        self._health_task = asyncio.create_task(self._health_loop())

    async def _health_loop(self) -> None:
        while True:
            await asyncio.sleep(self._float_config("health_check_interval", 300, 10, 600))
            await self._refresh_health()

    async def _refresh_health(self, force: bool = False) -> MemeManagerHealth:
        health = check_meme_manager_health(self.context, self.store)
        changed = health.status != self._health.status
        self._health = health
        self._last_health_check = time.monotonic()
        if health.ready:
            self._schedule_library_index()
        if force or changed:
            if health.ready:
                logger.info("[meme_stealer] meme_manager 已就绪: %s", health.summary())
            else:
                logger.warning("[meme_stealer] meme_manager 不可用: %s", health.summary())
        return health

    async def _manager_ready(self) -> bool:
        interval = self._float_config("health_check_interval", 300, 10, 600)
        if time.monotonic() - self._last_health_check >= interval:
            await self._refresh_health()
        return self._health.ready

    async def _claim_auto_send(self, event: AstrMessageEvent) -> bool:
        """Allow only one automatic send attempt for one incoming event."""
        key = event_identity(event)
        async with self._auto_send_claim_lock:
            if key in self._auto_send_claims:
                logger.debug("[meme_stealer] 跳过同一事件的重复表情包发送 event=%s", key)
                return False
            self._auto_send_claims[key] = time.monotonic()
            if len(self._auto_send_claims) > 1024:
                oldest = min(self._auto_send_claims, key=self._auto_send_claims.get)
                self._auto_send_claims.pop(oldest, None)
            return True

    def _schedule_library_index(self) -> None:
        """Schedule an idempotent scan when meme_manager is healthy."""
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
        self._library_task = asyncio.create_task(self._ensure_library_index())
        self._library_task.add_done_callback(self._log_library_task_failure)

    @staticmethod
    def _log_library_task_failure(task: asyncio.Task) -> None:
        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return
        if exception:
            logger.error("[meme_stealer] 后台表情包索引任务异常: %s", exception)

    @filter.event_message_type(EventMessageType.ALL)
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
        if getattr(event, "_meme_stealer_manual", False):
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
            logger.warning("[meme_stealer] 无法读取消息链", exc_info=True)
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

    @filter.command("偷取", priority=100000)
    async def steal_command(self, event: AstrMessageEvent):
        """Process images attached to the same message as /偷取 immediately."""
        setattr(event, "_meme_stealer_manual", True)
        if not await self._manager_ready():
            yield event.plain_result("meme_manager 当前不可用，暂时无法偷取。")
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
        if not self._bool_config("proactive_send_after_steal", False):
            return
        if not any(status in {"saved", "duplicate"} for status in results):
            return
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        image_path = self._last_stolen_image.get(umo)
        if not umo or image_path is None or not image_path.is_file():
            return
        try:
            message_chain = MessageChain().file_image(str(image_path))
            await self.context.send_message(umo, message_chain)
            logger.info("[meme_stealer] 偷取后主动发送表情包 path=%s", image_path)
        except Exception as exc:
            logger.warning("[meme_stealer] 偷取后主动发送失败: %s", exc, exc_info=True)

    @filter.command("发送表情包", priority=100000)
    @filter.command("发刚才的表情包", priority=100000)
    async def send_last_stolen_image(self, event: AstrMessageEvent):
        """Send the most recently saved meme from this chat session."""
        if not await self._manager_ready():
            yield event.plain_result("meme_manager 当前不可用，暂时无法发送表情包。")
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
        yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])

    @filter.command("表情偷取状态")
    async def status(self, event: AstrMessageEvent):
        """显示 meme_manager 依赖插件的加载与数据目录状态。"""
        health = await self._refresh_health(force=True)
        yield event.plain_result(health.summary())

    @filter.on_decorating_result(priority=100000)
    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        """Replace meme_manager's marker sender with this plugin's sender."""
        result = event.get_result()
        chain = getattr(result, "chain", None) if result else None
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
        force_send = explicit_meme_request(self._event_text(event))

        # Marker cleanup always happens, even if our own sender is disabled.
        if (
            not self._bool_config("auto_send_enabled", True)
            or (not plain_texts and not marked_categories and not force_send)
            or self._is_control_command(event)
            or not await self._manager_ready()
        ):
            return

        umo = str(getattr(event, "unified_msg_origin", "") or "")
        cooldown = self._float_config("auto_send_cooldown", 30, 0, 3600)
        if (
            cooldown
            and not force_send
            and time.monotonic() - self._last_auto_send.get(umo, 0) < cooldown
        ):
            return

        probability = self._float_config("auto_send_probability", 35, 0, 100)
        if not force_send and (probability <= 0 or random.random() * 100 >= probability):
            return
        if not await self._claim_auto_send(event):
            return
        image_path = await self._choose_outgoing_meme_from_index(
            event,
            "\n".join(plain_texts),
            force_send=force_send,
            preferred_categories=marked_categories,
        )
        if image_path is None:
            logger.debug("[meme_stealer] 情景模型未选择可发送表情包")
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
        self._pending_auto_images[event_identity(event)] = (umo, image_path)
        logger.info(
            "[meme_stealer] 已锁定表情包，等待正文发送完成 source=%s category=%s file=%s "
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

    @filter.after_message_sent(priority=0)
    async def after_message_sent(self, event: AstrMessageEvent) -> None:
        """Send a selected meme only after the text response is sent."""
        key = event_identity(event)
        pending = self._pending_auto_images.pop(key, None)
        if pending is None:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            for pending_key, candidate in list(self._pending_auto_images.items()):
                if candidate[0] == umo:
                    pending = self._pending_auto_images.pop(pending_key)
                    break
        if pending is None:
            return

        umo, image_path = pending
        if not image_path.is_file():
            logger.warning("[meme_stealer] deferred meme file is missing: %s", image_path)
            return
        try:
            await self.context.send_message(
                umo,
                MessageChain().file_image(str(image_path)),
            )
            self._last_auto_send[umo] = time.monotonic()
            logger.info("[meme_stealer] text sent; deferred meme sent file=%s", image_path)
            if self._bool_config("stop_agent_after_meme", True):
                if stop_event_propagation(event):
                    logger.info(
                        "[meme_stealer] stopped later agent handlers after sending meme"
                    )
        except Exception as exc:
            logger.warning("[meme_stealer] deferred meme send failed: %s", exc)

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
                if self.store.find_duplicate(payload.content, threshold) is not None:
                    logger.debug("[meme_stealer] 图片在识别前已存在，跳过模型调用")
                    statuses[index] = "duplicate"
                    continue
                if any(
                    self.store.is_similar(payload.content, previous.content, threshold)
                    for _previous_index, previous, _previous_path in loaded
                ):
                    logger.debug("[meme_stealer] current message contains a perceptual duplicate")
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
                        "[meme_stealer] 视觉批量调用失败，回退逐张识别: %s",
                        exc,
                    )
                    visions = {
                        index: await self._recognize_image(event, temp_path, message_text)
                        for index, temp_path in image_paths
                    }
                accepted = {
                    index: vision
                    for index, vision in visions.items()
                    if not self._should_skip(vision)
                }
                for index in visions:
                    if index not in accepted:
                        statuses[index] = "not_meme"
                        logger.info("[meme_stealer] 图片未被识别为表情包，跳过保存 index=%s", index)
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
                        "[meme_stealer] 情景批量调用失败，回退逐张分类: %s",
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
                        logger.info(
                            "[meme_stealer] 已收集表情包 category=%s path=%s",
                            category,
                            result.path,
                        )
                    else:
                        logger.debug("[meme_stealer] 跳过重复表情包 path=%s", result.path)
                return statuses
            except Exception:
                logger.error("[meme_stealer] 批量处理群聊图片失败", exc_info=True)
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
        if len(result) != len(images):
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
        if len(result) != len(visions):
            raise ValueError("batch scene response is missing image ids")
        return result

    async def _ensure_library_index(self) -> None:
        """Index missing or stale images without changing their category folders."""
        if self._library_lock.locked():
            return
        async with self._library_lock:
            categories = sorted(self.store.directory_categories())
            total = sum(len(self.store.image_paths(category)) for category in categories)
            if not total:
                return
            provider_id = configured_provider_id(
                self.config,
                "library_index_provider_id",
                "vision_provider_id",
            )
            if not provider_id:
                return
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
                catalog_is_current = all(
                    old_catalog.get(key) == value
                    for key, value in index_metadata.items()
                )
                records: list[tuple[Path, dict]] = []
                pending: list[tuple[Path, str]] = []
                for path in paths:
                    digest = self.store.image_digest(path)
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
                        logger.warning(
                            "[meme_stealer] 自动索引批次失败 category=%s count=%s: %s",
                            category,
                            len(batch),
                            exc,
                        )
                        logger.warning(
                            "[meme_stealer] stopping this library-index run after the first failed batch"
                        )
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
                            "[meme_stealer] 自动索引进度 %s 分类=%s 批量=%s",
                            self._progress_text(processed, total, errors),
                            category,
                            len(batch),
                        )

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
                self.store.write_catalog(category, entries, index_metadata)
            logger.info(
                "[meme_stealer] 自动索引检查完成 total=%s newly_classified=%s errors=%s",
                total,
                classified,
                errors,
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
        items = parsed.get("items", [])
        if not isinstance(items, list):
            raise ValueError("batch model response items is not a list")
        by_id = {
            str(item.get("id", "")): item
            for item in items
            if isinstance(item, dict) and item.get("id")
        }
        result: dict[Path, dict] = {}
        for path, image_id in image_ids.items():
            item = by_id.get(image_id)
            if item is None:
                continue
            tags = item.get("tags", [])
            if isinstance(tags, str):
                tags = [part.strip() for part in re.split(r"[,，、]", tags) if part.strip()]
            if not isinstance(tags, list):
                tags = []
            result[path] = {
                "description": str(item.get("description", "") or "")[:120],
                "emotion": str(item.get("emotion", "") or "")[:40],
                "text": str(item.get("text", "") or "")[:120],
                "tags": [str(tag)[:30] for tag in tags[:8] if str(tag).strip()],
                "indexed": True,
            }
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
                "[meme_stealer] 情景分析没有可用索引 category_hint=%s",
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
                    "[meme_stealer] 明确请求覆盖模型的不发送判断，继续选择分类"
                )
            if not force_send and not model_should_send:
                logger.info(
                    "[meme_stealer] 情景分析决定不发送 confidence=%s reason=%s",
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
                    "[meme_stealer] 情景分析选择了不存在的分类 category=%s reason=%s",
                    category,
                    reason,
                )
                return None

            image_path = self.store.pick_indexed_image(category)
            if image_path is None:
                logger.warning(
                    "[meme_stealer] 分类索引没有可用图片 category=%s",
                    category,
                )
                return None
            details = self._image_details(image_path)
            logger.info(
                "[meme_stealer] 情景分析决定发送 category=%s confidence=%s "
                "reason=%s description=%s indexed_count=%s",
                category,
                confidence,
                reason,
                details["description"],
                selected["indexed_count"],
            )
            return image_path
        except Exception as exc:
            logger.warning("[meme_stealer] 分类索引发送决策失败，不发送表情包: %s", exc)
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
                    "[meme_stealer] 情景分析决定不发送 confidence=%s reason=%s",
                    confidence,
                    reason,
                )
                return None
            candidate_id = str(choice.get("candidate_id", "")).strip()
            for item in candidates:
                if candidate_id in {item["id"], item["filename"]}:
                    details = self._image_details(item["path"])
                    logger.info(
                        "[meme_stealer] 情景分析决定发送 category=%s candidate=%s "
                        "confidence=%s reason=%s description=%s",
                        details["category"],
                        candidate_id,
                        confidence,
                        reason,
                        details["description"],
                    )
                    return item["path"]
            logger.warning(
                "[meme_stealer] 情景分析选择了不存在的候选 candidate=%s reason=%s",
                candidate_id,
                reason,
            )
        except Exception as exc:
            logger.warning("[meme_stealer] 单次智能回复决策失败，不发送表情包: %s", exc)
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
        }

    @staticmethod
    def _library_index_metadata(provider_id: str) -> dict:
        return {
            "index_version": LIBRARY_INDEX_VERSION,
            "index_prompt_version": LIBRARY_INDEX_PROMPT_VERSION,
            "index_provider_id": provider_id,
        }

    @staticmethod
    def _catalog_entry_is_current(entry: dict | None, provider_id: str) -> bool:
        if not isinstance(entry, dict) or not entry.get("indexed", False):
            return False
        metadata = MemeStealer._library_index_metadata(provider_id)
        return all(entry.get(key) == value for key, value in metadata.items())

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
            logger.warning("[meme_stealer] 视觉模型失败，转入降级分类: %s", exc)
            return {"is_meme": True, "confidence": 0, "description": "视觉模型不可用"}

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
            logger.warning("[meme_stealer] 情景模型失败，将使用 fallback_category: %s", exc)
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
        if not path.is_file():
            logger.debug("[meme_stealer] 图片来源不存在: %s", source)
            return None
        content = path.read_bytes()
        if len(content) > limit:
            logger.warning("[meme_stealer] 图片超过大小限制: %s", path)
            return None
        payload = self._payload_from_content(content, limit)
        if payload is None:
            logger.warning("[meme_stealer] local file is not a valid image: %s", path)
        return payload

    async def _download_image(self, source: str, limit: int) -> ImagePayload | None:
        timeout = aiohttp.ClientTimeout(total=self._float_config("download_timeout", 20, 5, 120))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(source) as response:
                    response.raise_for_status()
                    content_length = int(response.headers.get("Content-Length", "0") or 0)
                    if content_length > limit:
                        logger.warning("[meme_stealer] 远程图片超过大小限制: %s", source)
                        return None
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        total += len(chunk)
                        if total > limit:
                            logger.warning("[meme_stealer] 远程图片超过大小限制: %s", source)
                            return None
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    payload = self._payload_from_content(content, limit)
                    if payload is None:
                        logger.warning(
                            "[meme_stealer] downloaded content is not a valid image: %s content_type=%s",
                            source,
                            response.headers.get("Content-Type", ""),
                        )
                    return payload
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.warning("[meme_stealer] 下载图片失败 %s: %s", source, exc)
            return None

    @staticmethod
    def _decode_data_url(source: str, limit: int) -> ImagePayload | None:
        match = re.match(r"data:image/([a-zA-Z0-9.+-]+);base64,(.+)", source, re.DOTALL)
        if not match:
            return None
        return MemeStealer._decode_base64(match.group(2), limit)

    @staticmethod
    def _decode_base64(value: str, limit: int) -> ImagePayload | None:
        try:
            content = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            return None
        return MemeStealer._payload_from_content(content, limit)

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
        is_meme = vision.get("is_meme")
        if isinstance(is_meme, str):
            is_meme = is_meme.strip().lower() not in {"false", "no", "0"}
        if is_meme is not False:
            return False
        try:
            confidence = float(vision.get("confidence", 1))
        except (TypeError, ValueError):
            confidence = 1
        return confidence >= float(self.config.get("meme_rejection_confidence", 0.7) or 0.7)

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
        return MemeStealer._event_text(event)

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
            logger.error("[meme_stealer] 后台任务异常: %s", exception)

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
