"""Capture orchestration pipeline.

Owns the multi-image batch flow (load, dedupe, recognize, classify, save)
without registering any AstrBot filters.  Leaf primitives (image loading,
single-image recognition/classification, catalog entry building, event-state
binding) are injected through the constructor, keeping this module free of
WebUI and direct filesystem write primitives.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any, Callable

from astrbot.api import logger

from .collector import (
    MEME_CAPTURE_RUBRIC,
    complete_batch_indices,
    configured_provider_id,
    normalize_category,
    parse_model_json,
)
from .backend.tagging import (
    PRIMARY_CATEGORIES,
    normalize_primary_category,
    normalize_semantic_tags,
    normalize_tags,
)


VISION_BATCH_SYSTEM_PROMPT = f"""
你是群聊表情包批量视觉识别器。输入包含多张图片，请逐张输出结果，必须保留每张图片的 id。
只保留高置信度、明确用于聊天表达情绪/反应/吐槽/文字梗的表情包。截图、聊天记录截图、网页或软件界面、文档、海报、普通照片、风景照和没有表达意图的图片都不是表情包；无法确认时宁可拒绝。
{MEME_CAPTURE_RUBRIC}
每张图片必须给出内容类型和排除标记。
只输出 JSON，不要 Markdown。
格式：{{"items":[{{"id":"image_0", "is_meme":true, "confidence":0.0, "meme_score":0, "content_type":"reaction_meme", "has_expression":true, "is_screenshot":false, "is_chat_screenshot":false, "is_document":false, "is_ui":false, "is_photo":false, "is_webpage":false, "is_poster":false, "is_banner":false, "is_receipt":false, "rejection_reason":"不合格时填写原因，否则为空", "description":"简短中文描述", "emotion":"情绪", "text":"图片文字"}}]}}
content_type 只能是 reaction_meme、expression_meme、text_meme、sticker_meme、animated_meme、meme 之一；不属于这些类型时 is_meme 必须为 false。
""".strip()


def _scene_batch_system_prompt(categories: set[str]) -> str:
    category_text = ", ".join(sorted(categories))
    return f"""
你是群聊表情包批量情景分类器。输入包含多张图片的识别结果和同一条消息语境。
请为每个图片 id 选择一个最合适的分类，只能从以下分类中选择：{category_text}
只输出 JSON，不要 Markdown。
格式：{{"items":[{{"id":"image_0", "category":"分类名", "confidence":0.0, "reason":"不超过30字"}}]}}
""".strip()


class CapturePipeline:
    """Coordinate one message's images through the capture state machine."""

    def __init__(
        self,
        *,
        store: Any,
        config: Any,
        semaphore: asyncio.Semaphore,
        save_lock: asyncio.Lock,
        generate: Callable[..., Any],
        activity_recorder: Callable[..., Any],
        loader: Callable[..., Any],
        recognize_single: Callable[..., Any],
        classify_single: Callable[..., Any],
        should_skip: Callable[[dict], bool],
        catalog_entry_builder: Callable[..., dict],
        bind_saved_result: Callable[..., None],
        capture_blacklist: Any | None = None,
    ):
        self.store = store
        self.config = config
        self._semaphore = semaphore
        self._save_lock = save_lock
        self._generate = generate
        self._record_capture_event = activity_recorder
        self._loader = loader
        self._recognize_single = recognize_single
        self._classify_single = classify_single
        self._should_skip = should_skip
        self._catalog_entry_builder = catalog_entry_builder
        self._bind_saved_result = bind_saved_result
        self._capture_blacklist = capture_blacklist

    def _duplicate_threshold(self) -> int | None:
        if not self.config.perceptual_dedupe_enabled:
            return None
        return self.config.perceptual_duplicate_threshold

    async def process_one(
        self,
        event: Any,
        source: str,
        message_text: str,
        message_outline: str,
    ) -> str:
        results = await self.process_batch(
            event, [source], message_text, message_outline
        )
        return results[0] if results else "error"

    async def process_batch(
        self,
        event: Any,
        sources: list[str],
        message_text: str,
        message_outline: str,
    ) -> list[str]:
        """Process all new images in one message with two batched model calls."""
        async with self._semaphore:
            statuses = ["error"] * len(sources)
            loaded: list[tuple[int, Any, Any]] = []
            for index, source in enumerate(sources):
                try:
                    payload = await self._loader(source)
                except Exception:
                    payload = None
                if payload is None:
                    statuses[index] = "unavailable"
                    continue
                digest = hashlib.sha256(payload.content).hexdigest()
                if self._capture_blacklist is not None:
                    try:
                        if self._capture_blacklist.contains(digest):
                            statuses[index] = "blacklisted"
                            continue
                    except ValueError as exc:
                        logger.error("[meme_manager_master] 捕获黑名单不可用，拒绝保存图片: %s", exc)
                        statuses[index] = "blacklisted"
                        continue
                threshold = self._duplicate_threshold()
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
                primary_categories = getattr(self.store, "available_primary_categories", None)
                categories = (
                    set(primary_categories())
                    if callable(primary_categories)
                    else set(PRIMARY_CATEGORIES)
                )
                if not categories:
                    categories = set(PRIMARY_CATEGORIES)
                image_paths = [
                    (index, temp_path) for index, _payload, temp_path in loaded
                ]
                try:
                    if len(image_paths) == 1:
                        index, temp_path = image_paths[0]
                        visions = {
                            index: await self._recognize_single(
                                event, temp_path, message_text
                            )
                        }
                    else:
                        visions = await self._recognize_batch(
                            event, image_paths, message_text
                        )
                except Exception as exc:
                    logger.warning(
                        "[meme_manager_master] 视觉批量调用失败，回退逐张识别: %s",
                        exc,
                    )
                    visions = {
                        index: await self._recognize_single(
                            event, temp_path, message_text
                        )
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
                            index: await self._classify_single(
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
                        index: await self._classify_single(
                            event,
                            vision,
                            categories,
                            message_text,
                            message_outline,
                        )
                        for index, vision in accepted.items()
                    }
                payload_by_index = {index: payload for index, payload, _path in loaded}
                fallback = normalize_primary_category(self.config.fallback_category) or "疑惑"
                for index, vision in accepted.items():
                    scene = scenes.get(index, {})
                    scene_category = normalize_primary_category(scene.get("category"))
                    category = normalize_category(
                        scene_category or scene.get("category"), categories, fallback
                    )
                    semantic_tags = normalize_semantic_tags(
                        [
                            scene.get("semantic_tags"),
                            scene.get("tags"),
                            vision.get("semantic_tags"),
                            vision.get("tags"),
                        ]
                    )
                    tags = normalize_tags(
                        [category, scene.get("tags"), vision.get("tags")]
                    )
                    scene = {
                        **scene,
                        "category": category,
                        "primary_category": category,
                        "semantic_tags": semantic_tags,
                    }
                    payload = payload_by_index[index]
                    async with self._save_lock:
                        digest = hashlib.sha256(payload.content).hexdigest()
                        save = lambda: self.store.save_image(
                            payload.content, tags, payload.extension, self._duplicate_threshold()
                        )
                        if self._capture_blacklist is None:
                            allowed, result = True, save()
                        else:
                            try:
                                allowed, result = self._capture_blacklist.run_if_allowed(digest, save)
                            except ValueError as exc:
                                logger.error("[meme_manager_master] 捕获黑名单不可用，拒绝保存图片: %s", exc)
                                allowed, result = False, None
                        if not allowed or result is None:
                            statuses[index] = "blacklisted"
                            continue
                        if result.status in {"saved", "duplicate"}:
                            self._bind_saved_result(event, result.path)
                        statuses[index] = result.status
                        if result.status in {"saved", "duplicate"}:
                            catalog_entry = self._catalog_entry_builder(
                                result.path, category, vision, scene
                            )
                            catalog_entry["perceptual_hash"] = (
                                self.store.image_perceptual_hash(result.path)
                            )
                            if result.status == "saved":
                                self.store.upsert_catalog_entry(
                                    category,
                                    catalog_entry,
                                )
                                self._record_capture_event(
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
                                self.store.merge_catalog_entry(
                                    catalog_entry,
                                    digest=result.digest,
                                    tags=tags,
                                )
                                self._record_capture_event(
                                    self.store.root,
                                    category=category,
                                    filename=result.path.name,
                                    digest=result.digest,
                                    status="duplicate",
                                    duplicate_of=result.path.name,
                                )
                                logger.debug(
                                    "[meme_manager_master] 跳过重复表情包 path=%s", result.path
                                )
                return statuses
            except Exception:
                logger.error("[meme_manager_master] 批量处理群聊图片失败", exc_info=True)
                return [
                    status if status != "error" else "error" for status in statuses
                ]
            finally:
                for _index, _payload, temp_path in loaded:
                    self.store.remove_temp_file(temp_path)

    async def _recognize_batch(
        self,
        event: Any,
        images: list[tuple[int, Any]],
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
        event: Any,
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
