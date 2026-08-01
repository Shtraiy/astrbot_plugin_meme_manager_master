"""Catalog index service: captions, manual review and capture workspace.

This service owns the catalog-facing operations that previously lived on the
vector semantic task manager: manual review, single-image semantic saving,
category confirmation and revision proposals.  It never imports FAISS and is
always available, so the default install keeps the catalog review and capture
workspace working without vector dependencies.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .semantic_caption import generate_caption
from .semantic_models import REVIEW_CATEGORY, is_category_tag, utc_now
from .semantic_storage import (
    confirm_image_category,
    load_category_descriptions,
    restore_image_auto_semantic,
    save_manual_image_semantic,
    save_manual_image_semantic_and_move,
    validate_image_edit_snapshot,
)


VECTOR_CAPABILITY_ERROR = (
    "向量语义能力未启用：请启用 vector_semantic_enabled 配置并安装 faiss-cpu。"
)


class CatalogIndexService:
    """Pack-scoped catalog operations with a per-pack mutation guard."""

    def __init__(
        self,
        plugin_data_dir: Path | str,
        *,
        context: Any = None,
        config: dict | None = None,
    ):
        self.plugin_data_dir = Path(plugin_data_dir).resolve()
        self.context = context
        self.config = config or {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._external_pack_operations: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Mutation guard (pack-level, mirrors the retired semantic manager)
    # ------------------------------------------------------------------
    def _lock(self, pack_id: str) -> asyncio.Lock:
        return self._locks.setdefault(pack_id, asyncio.Lock())

    @staticmethod
    def _validate_pack_id(pack_id: str) -> str:
        value = str(pack_id or "").strip()
        if not value or not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", value):
            raise ValueError("pack_id 无效")
        return value

    def _pack_dir(self, pack_id: str) -> Path:
        return self.plugin_data_dir / "packs" / str(pack_id)

    def begin_external_pack_operation(self, pack_id: str, operation: str) -> None:
        """Register an external file task so catalog mutations are blocked."""
        pack_id = self._validate_pack_id(pack_id)
        self.assert_pack_mutation_allowed(pack_id, operation)
        self._external_pack_operations[pack_id] = str(operation or "外部文件任务")

    def end_external_pack_operation(self, pack_id: str) -> None:
        self._external_pack_operations.pop(str(pack_id or "").strip(), None)

    def assert_pack_mutation_allowed(
        self, pack_id: str, operation: str = "修改资源包"
    ) -> None:
        """Reject mutations while another file task owns the pack."""
        pack_id = self._validate_pack_id(pack_id)
        external_operation = self._external_pack_operations.get(pack_id)
        if external_operation:
            raise RuntimeError(
                f"资源包 {pack_id} 正在执行“{external_operation}”，暂时不能{operation}"
            )

    async def run_locked_pack_mutation(
        self, pack_id: str, operation: str, mutation: Any
    ) -> Any:
        """Run a synchronous pack mutation inside the per-pack guard."""
        pack_id = self._validate_pack_id(pack_id)
        if not callable(mutation):
            raise TypeError("mutation 必须可调用")
        async with self._lock(pack_id):
            self.assert_pack_mutation_allowed(pack_id, operation)
            return mutation()

    # ------------------------------------------------------------------
    # Vision provider + usage tracking (shared with the vector manager)
    # ------------------------------------------------------------------
    def _state_path(self, pack_id: str) -> Path:
        return (
            self.plugin_data_dir / "semantic_indexes" / str(pack_id) / "task_state.json"
        )

    def _load_state(self, pack_id: str) -> dict[str, Any]:
        path = self._state_path(pack_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self, pack_id: str, state: dict[str, Any]) -> None:
        atomic_write_json(self._state_path(pack_id), state)

    @staticmethod
    def _normalize_token_usage(value: Any) -> dict[str, int]:
        if not isinstance(value, dict):
            value = {}
        result: dict[str, int] = {}
        for key in ("input", "output", "total", "calls"):
            try:
                result[key] = max(0, int(value.get(key, 0) or 0))
            except (TypeError, ValueError):
                result[key] = 0
        if result["total"] <= 0:
            result["total"] = result["input"] + result["output"]
        return result

    def _record_vision_usage(self, pack_id: str, usage: Any) -> None:
        state = self._load_state(pack_id)
        total = self._normalize_token_usage(state.get("token_usage"))
        current = self._normalize_token_usage(usage)
        for key in ("input", "output", "total"):
            total[key] += current[key]
        total["calls"] += max(1, current["calls"])
        state["token_usage"] = total
        state["vision_calls"] = total["calls"]
        state["updated_at"] = utc_now()
        self._save_state(pack_id, state)

    def _vision_provider_details(self) -> dict[str, str | bool]:
        provider_id = str(
            self.config.get("vision_provider_id")
            or self.config.get("visual_provider_id")
            or ""
        ).strip()
        details: dict[str, str | bool] = {
            "id": provider_id,
            "model": "",
            "ready": False,
        }
        if not provider_id or self.context is None:
            return details
        resolver = getattr(self.context, "get_provider_by_id", None)
        if not callable(resolver) or not callable(
            getattr(self.context, "llm_generate", None)
        ):
            return details
        try:
            provider = resolver(provider_id)
        except Exception:
            provider = None
        if provider is None:
            return details
        provider_config = getattr(provider, "provider_config", {})
        modalities = (
            provider_config.get("modalities")
            if isinstance(provider_config, dict)
            else None
        )
        if isinstance(modalities, list) and modalities:
            if "image" not in {
                str(value or "").strip().lower() for value in modalities
            }:
                return details
        model = ""
        meta = getattr(provider, "meta", None)
        if callable(meta):
            try:
                model = str(getattr(meta(), "model", "") or "")
            except Exception:
                model = ""
        if not model:
            for key in ("model", "model_name", "chat_model"):
                if isinstance(provider_config, dict) and provider_config.get(key):
                    model = str(provider_config[key])
                    break
        details.update({"model": model, "ready": True})
        return details

    def _vision_provider_ready(self) -> bool:
        return bool(self._vision_provider_details()["ready"])

    def _safe_error(self, error: Any, pack_id: str = "") -> str:
        message = str(error or "未知错误")
        for secret_path in (str(self.plugin_data_dir), str(self._pack_dir(pack_id))):
            if secret_path:
                message = message.replace(secret_path, "<本地资源>")
        return message[:500]

    # ------------------------------------------------------------------
    # Catalog operations
    # ------------------------------------------------------------------
    async def confirm_category(
        self,
        pack_id: str,
        image_path: Path | str,
        *,
        expected_content_sha256: str = "",
        expected_entry_id: str = "",
    ) -> dict[str, Any]:
        """Confirm the current category inside the pack mutation guard."""
        pack_id = self._validate_pack_id(pack_id)
        async with self._lock(pack_id):
            self.assert_pack_mutation_allowed(pack_id, "确认图片分类")
            return confirm_image_category(
                self._pack_dir(pack_id),
                image_path,
                expected_content_sha256=expected_content_sha256,
                expected_entry_id=expected_entry_id,
            )

    async def save_image_manual_semantic(
        self,
        pack_id: str,
        image_path: Path | str,
        *,
        caption: str,
        tags: Any,
        visible_text: str = "",
        category_decision: str = "keep",
        expected_content_sha256: str = "",
        expected_entry_id: str = "",
        update_vector: bool = False,
        target_category: str = "",
    ) -> dict[str, Any]:
        """Save one image's manual catalog semantic (without vectors)."""
        if update_vector:
            raise RuntimeError(VECTOR_CAPABILITY_ERROR)
        pack_id = self._validate_pack_id(pack_id)
        pack_dir = self._pack_dir(pack_id)
        normalized_target = str(target_category or "").strip()
        async with self._lock(pack_id):
            operation = (
                "保存图片人工语义并移动分类"
                if normalized_target
                else "保存图片人工语义"
            )
            self.assert_pack_mutation_allowed(pack_id, operation)
            if normalized_target:
                move_result = save_manual_image_semantic_and_move(
                    pack_dir,
                    image_path,
                    normalized_target,
                    caption=caption,
                    tags=tags,
                    visible_text=visible_text,
                    expected_content_sha256=expected_content_sha256,
                    expected_entry_id=expected_entry_id,
                )
                detail = move_result["semantic"]
            else:
                detail = save_manual_image_semantic(
                    pack_dir,
                    image_path,
                    caption=caption,
                    tags=tags,
                    visible_text=visible_text,
                    category_decision=category_decision,
                    expected_content_sha256=expected_content_sha256,
                    expected_entry_id=expected_entry_id,
                )
                move_result = {}
            return {
                "semantic": detail,
                "semantic_saved": True,
                "moved": bool(move_result),
                "source_category": str(move_result.get("source_category") or ""),
                "target_category": str(move_result.get("target_category") or ""),
                "category": str(detail.get("category") or ""),
                "filename": Path(str(detail.get("relative_path") or "")).name,
                "vector_update": {
                    "status": "unavailable",
                    "provider_available": False,
                    "message": VECTOR_CAPABILITY_ERROR,
                },
            }

    async def restore_image_auto_semantic(
        self,
        pack_id: str,
        image_path: Path | str,
        *,
        expected_content_sha256: str = "",
        expected_entry_id: str = "",
    ) -> dict[str, Any]:
        """Drop the manual semantic for one image inside the guard."""
        pack_id = self._validate_pack_id(pack_id)
        async with self._lock(pack_id):
            self.assert_pack_mutation_allowed(pack_id, "恢复图片自动语义")
            return restore_image_auto_semantic(
                self._pack_dir(pack_id),
                image_path,
                expected_content_sha256=expected_content_sha256,
                expected_entry_id=expected_entry_id,
            )

    async def propose_image_semantic_revision(
        self,
        pack_id: str,
        image_path: Path | str,
        *,
        review_instruction: str,
        expected_content_sha256: str = "",
        expected_entry_id: str = "",
    ) -> dict[str, Any]:
        """Call the vision model and return a revision candidate (no writes)."""
        from .semantic_task import _revision_category_choice, _revision_original_category

        instruction = str(review_instruction or "").strip()
        if not instruction:
            raise ValueError("请先填写人工复审意见")
        if len(instruction) > 2000:
            raise ValueError("人工复审意见不能超过 2000 个字符")
        pack_id = self._validate_pack_id(pack_id)
        pack_dir = self._pack_dir(pack_id)
        async with self._lock(pack_id):
            self.assert_pack_mutation_allowed(pack_id, "调用视觉模型重写图片语义")
            vision = self._vision_provider_details()
            if not vision["ready"]:
                raise RuntimeError("当前没有可用的视觉模型，请先在插件配置中选择")
            snapshot = validate_image_edit_snapshot(
                pack_dir,
                image_path,
                expected_content_sha256=expected_content_sha256,
                expected_entry_id=expected_entry_id,
            )
            item = snapshot["item"]
            category_descriptions = load_category_descriptions(pack_dir)
            memes_root = pack_dir / "memes"
            category_paths = (
                [
                    category_path
                    for category_path in memes_root.iterdir()
                    if category_path.is_dir() and not category_path.is_symlink()
                ]
                if memes_root.is_dir()
                else []
            )
            for category_path in category_paths:
                category_descriptions.setdefault(category_path.name, "")
            selectable_categories = {
                category_path.name
                for category_path in category_paths
                if category_path.name and category_path.name != REVIEW_CATEGORY
            }
            available_categories = {
                category: description
                for category, description in category_descriptions.items()
                if category in selectable_categories
            }
            original_category = _revision_original_category(
                item,
                selectable_categories,
            )
            try:
                proposal = await generate_caption(
                    self.context,
                    snapshot["source"],
                    str(vision["id"]),
                    category=item.category,
                    category_description=item.category_description,
                    available_categories=available_categories,
                    review_instruction=instruction,
                    current_semantic={
                        "caption": item.caption,
                        "tags": [tag for tag in item.tags if not is_category_tag(tag)],
                        "visible_text": item.visible_text,
                        "current_category": item.category,
                        "original_category": original_category,
                        "reclassification_status": item.reclassification_status,
                        "reclassification_reason": item.reclassification_reason,
                    },
                )
            except Exception as exc:
                self._record_vision_usage(
                    pack_id,
                    getattr(exc, "token_usage", None),
                )
                raise
            self._record_vision_usage(pack_id, proposal.get("token_usage"))
            validate_image_edit_snapshot(
                pack_dir,
                image_path,
                expected_content_sha256=snapshot["content_sha256"],
                expected_entry_id=snapshot["entry_id"],
            )
            category_fit = str(proposal.get("category_fit") or "uncertain")
            suggested_category = str(proposal.get("suggested_category") or "").strip()
            selected_category, classification_action = _revision_category_choice(
                current_category=item.category,
                original_category=original_category,
                category_fit=category_fit,
                suggested_category=suggested_category,
                selectable_categories=selectable_categories,
            )
            return {
                "caption": str(proposal.get("caption") or "").strip(),
                "tags": [
                    tag for tag in proposal.get("tags", []) if not is_category_tag(tag)
                ],
                "visible_text": str(proposal.get("visible_text") or "").strip(),
                "category_fit": category_fit,
                "category_review_reason": str(
                    proposal.get("category_review_reason") or ""
                ).strip(),
                "suggested_category": suggested_category,
                "current_category": item.category,
                "original_category": original_category,
                "selected_category": selected_category,
                "classification_action": classification_action,
                "vision_model": str(proposal.get("vision_model") or vision["id"]),
                "vision_requests": int(
                    (proposal.get("token_usage") or {}).get("calls", 1) or 1
                ),
            }
