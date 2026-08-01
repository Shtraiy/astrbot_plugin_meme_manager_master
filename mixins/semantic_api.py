from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import io
import json
import mimetypes
import re
import secrets
import time
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from quart import jsonify, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from astrbot.api import logger

from ..capture_activity import load_capture_activity
from ..backend.models import (
    DuplicateEmojiError,
    add_emoji_to_category,
    batch_copy_emojis,
    batch_delete_emojis,
    batch_move_emojis,
    clear_all_emojis,
    clear_category_emojis,
    delete_emoji_from_category,
    get_emoji_by_category,
    move_emoji_to_category,
    scan_emoji_folder,
)
from ..backend.pack_storage import (
    export_pack_archive,
    export_runtime_backup,
    fetch_and_cache_community_index,
    find_cached_pack_entry,
    get_pack_detail,
    get_pack_export_capabilities,
    get_selection_rules,
    import_pack_archive,
    import_runtime_backup,
    inspect_pack_archive,
    install_first_official_pack_from_index,
    install_pack_from_github_source,
    list_installed_packs,
    load_cached_community_index,
    save_selection_rules,
    set_default_pack,
    uninstall_pack,
)
from ..backend.semantic_index import EmbeddingAdapter, index_is_ready
from ..backend.semantic_storage import (
    get_category_review_overview,
    get_image_semantic_detail,
    import_metadata_file,
    invalidate_semantic_metadata,
    load_metadata,
    metadata_items,
)
from ..storage import (
    IMAGE_EXTENSIONS,
    MemeStore,
    image_preview_mode,
    is_safe_category_segment,
    scan_pack_emojis,
)
from ..config import (
    COMMUNITY_INDEX_URL,
    get_active_pack_paths,
    MEMES_DIR,
    PACKS_DIR,
    PLUGIN_DATA_DIR,
    TEMP_DIR,
)

PLUGIN_NAME = "meme_manager_master"
WEBUI_LOG_PREFIX = f"[{PLUGIN_NAME}][WebUI]"
MAX_PREVIEW_IMAGE_BYTES = 8 * 1024 * 1024
MAX_ORIGINAL_IMAGE_BYTES = 32 * 1024 * 1024
PREVIEW_IMAGE_MAX_DIMENSION = 512
PACK_IMPORT_SESSION_TTL_SECONDS = 60 * 60
MAX_PACK_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_PACK_UPLOAD_REQUEST_BYTES = MAX_PACK_ARCHIVE_BYTES + 1024 * 1024




class SemanticAPIMixin:
    async def _semantic_request_pack_id(self, data: dict | None = None) -> str:
        payload = data or {}
        pack_id = str(
            payload.get("pack_id")
            or request.args.get("pack_id")
            or request.args.get("managed_pack_id")
            or ""
        ).strip()
        if not pack_id:
            pack_id = str(
                getattr(self, "_resolve_runtime_pack_context", lambda: {})().get(
                    "pack_id"
                )
                or ""
            )
        if not pack_id:
            raise ValueError("pack_id 不能为空")
        if not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", pack_id):
            raise ValueError("pack_id 无效")
        pack_dir = (PACKS_DIR / pack_id).resolve()
        try:
            pack_dir.relative_to(PACKS_DIR.resolve())
        except ValueError as exc:
            raise ValueError("pack_id 无效") from exc
        if not pack_dir.is_dir():
            raise FileNotFoundError(f"表情包 {pack_id} 不存在")
        return pack_id

    def _safe_semantic_image_name(value: str) -> bool:
        normalized = str(value or "").strip()
        return bool(
            normalized
            and normalized not in {".", ".."}
            and Path(normalized).name == normalized
            and "/" not in normalized
            and "\\" not in normalized
        )

    def _safe_image_filename(value: str) -> bool:
        normalized = str(value or "").strip()
        return (
            WebAPIMixin._safe_semantic_image_name(normalized)
            and Path(normalized).suffix.lower() in IMAGE_EXTENSIONS
        )

    async def _semantic_image_edit_request(
        self, data: dict[str, Any]
    ) -> tuple[str, str, str, Path]:
        pack_id = await self._semantic_request_pack_id(data)
        expected_pack_id = str(data.get("expected_pack_id") or "").strip()
        if not expected_pack_id:
            raise ValueError("缺少图包编辑快照，请重新打开图片后再操作")
        if expected_pack_id != pack_id:
            raise RuntimeError("当前图包已经切换，请重新打开图片后再编辑")
        expected_digest = str(data.get("expected_content_sha256") or "").strip().lower()
        expected_entry_id = str(data.get("expected_entry_id") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_digest) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_entry_id
        ):
            raise ValueError("图片编辑快照无效，请重新打开图片后再操作")
        category = str(data.get("category") or "").strip()
        filename = str(data.get("filename") or "").strip()
        if not self._safe_semantic_image_name(
            category
        ) or not self._safe_semantic_image_name(filename):
            raise ValueError("分类或文件名无效")
        pack_dir = (PACKS_DIR / pack_id).resolve()
        memes_root = (pack_dir / "memes").resolve()
        requested_image_path = memes_root / category / filename
        if requested_image_path.is_symlink():
            raise ValueError("不允许通过符号链接编辑图片")
        image_path = requested_image_path.resolve()
        try:
            image_path.relative_to(memes_root)
        except ValueError as exc:
            raise ValueError("图片路径无效") from exc
        return pack_id, category, filename, image_path

    async def _api_semantic_save_image(self):
        return await self._api_semantic_save_image_impl(update_vector=False)

    async def _api_semantic_save_image_and_vector(self):
        return await self._api_semantic_save_image_impl(update_vector=True)

    async def _api_semantic_propose_image_revision(self):
        try:
            data = await request.get_json() or {}
            (
                pack_id,
                category,
                filename,
                image_path,
            ) = await self._semantic_image_edit_request(data)
            proposal = await self.catalog_index_service.propose_image_semantic_revision(
                pack_id,
                image_path,
                review_instruction=str(data.get("review_instruction") or ""),
                expected_content_sha256=str(data.get("expected_content_sha256") or ""),
                expected_entry_id=str(data.get("expected_entry_id") or ""),
            )
            return jsonify(
                {
                    "message": "视觉模型已重写语义并选择分类候选；检查后请点击保存，当前语义尚未改变",
                    "pack_id": pack_id,
                    "category": category,
                    "filename": filename,
                    "proposal": proposal,
                }
            ), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except RuntimeError as exc:
            status = 503 if "没有可用的视觉模型" in str(exc) else 409
            return jsonify({"message": str(exc)}), status
        except Exception as exc:
            logger.error("按人工复审意见生成图片语义失败: %s", exc, exc_info=True)
            return jsonify({"message": f"视觉模型生成失败：{str(exc)[:300]}"}), 502

    async def _api_semantic_save_image_impl(self, *, update_vector: bool):
        try:
            data = await request.get_json() or {}
            (
                pack_id,
                category,
                filename,
                image_path,
            ) = await self._semantic_image_edit_request(data)
            service = (
                self.vector_semantic_service
                if update_vector
                else self.catalog_index_service
            )
            result = await service.save_image_manual_semantic(
                pack_id,
                image_path,
                caption=str(data.get("caption") or ""),
                tags=data.get("tags", []),
                visible_text=str(data.get("visible_text") or ""),
                category_decision=str(data.get("category_decision") or "keep"),
                expected_content_sha256=str(data.get("expected_content_sha256") or ""),
                expected_entry_id=str(data.get("expected_entry_id") or ""),
                update_vector=update_vector,
                target_category=str(data.get("target_category") or ""),
            )
            vector_status = str(result.get("vector_update", {}).get("status") or "")
            moved = bool(result.get("moved"))
            if not update_vector:
                message = "人工语义已保存，向量等待更新"
            elif vector_status == "done":
                message = (
                    "人工语义已保存，分类已移动，当前图片向量已更新"
                    if moved
                    else "人工语义已保存，当前图片向量已更新"
                )
            else:
                base_message = str(
                    result.get("vector_update", {}).get("message")
                    or "人工语义已保存，向量等待更新"
                )
                message = f"分类已移动；{base_message}" if moved else base_message
            return jsonify(
                {
                    "message": message,
                    "pack_id": pack_id,
                    "category": category,
                    "filename": filename,
                    **result,
                }
            ), 200
        except FileExistsError as exc:
            return jsonify({"message": str(exc)}), 409
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("保存图片人工语义失败: %s", exc, exc_info=True)
            return jsonify({"message": "保存图片人工语义失败"}), 500

    async def _api_semantic_restore_image_auto(self):
        try:
            data = await request.get_json() or {}
            (
                pack_id,
                category,
                filename,
                image_path,
            ) = await self._semantic_image_edit_request(data)
            detail = await self.catalog_index_service.restore_image_auto_semantic(
                pack_id,
                image_path,
                expected_content_sha256=str(data.get("expected_content_sha256") or ""),
                expected_entry_id=str(data.get("expected_entry_id") or ""),
            )
            return jsonify(
                {
                    "message": "已放弃当前图片的人工修改，恢复为自动生成状态",
                    "pack_id": pack_id,
                    "category": category,
                    "filename": filename,
                    "semantic": detail,
                }
            ), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("恢复图片自动语义失败: %s", exc, exc_info=True)
            return jsonify({"message": "恢复图片自动语义失败"}), 500

    async def _api_semantic_reviews(self):
        try:
            pack_id = await self._semantic_request_pack_id()
            return jsonify(
                {
                    "pack_id": pack_id,
                    **get_category_review_overview(PACKS_DIR / pack_id),
                }
            ), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取分类审核状态失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取分类审核状态失败"}), 500

    async def _api_semantic_confirm_category(self):
        try:
            data = await request.get_json() or {}
            (
                pack_id,
                category,
                filename,
                image_path,
            ) = await self._semantic_image_edit_request(data)
            detail = await self.catalog_index_service.confirm_category(
                pack_id,
                image_path,
                expected_content_sha256=str(data.get("expected_content_sha256") or ""),
                expected_entry_id=str(data.get("expected_entry_id") or ""),
            )
            return jsonify(
                {
                    "message": "已确认当前分类正确",
                    "pack_id": pack_id,
                    "category": category,
                    "filename": filename,
                    "semantic": detail,
                }
            ), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("确认图片分类失败: %s", exc, exc_info=True)
            return jsonify({"message": "确认图片分类失败"}), 500

    def _build_file_data_url(file_path, mime_type: str) -> str:
        with open(file_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _build_preview_data_url(file_path) -> tuple[str, str]:
        resample_filter = getattr(
            getattr(PILImage, "Resampling", PILImage),
            "LANCZOS",
            PILImage.BICUBIC,
        )
        with PILImage.open(file_path) as image:
            image.thumbnail(
                (PREVIEW_IMAGE_MAX_DIMENSION, PREVIEW_IMAGE_MAX_DIMENSION),
                resample_filter,
            )
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA")
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=82, method=4)
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/webp;base64,{encoded}", "image/webp"

    async def _api_semantic_status(self):
        try:
            pack_id = await self._semantic_request_pack_id()
            result = self.vector_semantic_service.status(pack_id)
            metadata = load_metadata(PACKS_DIR / pack_id)
            provider = EmbeddingAdapter(
                self.vector_semantic_service.resolve_embedding_provider(pack_id),
                str(getattr(self, "semantic_embedding_provider_id", "") or ""),
            )
            result["index_ready"] = index_is_ready(
                PLUGIN_DATA_DIR,
                pack_id,
                metadata,
                provider.provider_id,
                provider.model_name,
                provider.dimension,
            )
            result["semantic_enabled"] = bool(getattr(self, "semantic_enabled", False))
            result["semantic_config_ready"] = bool(
                not result["semantic_enabled"] or result.get("embedding_provider_ready")
            )
            return jsonify(result), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取语义状态失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取语义状态失败"}), 500

    async def _api_semantic_items(self):
        try:
            pack_id = await self._semantic_request_pack_id()
            try:
                page = max(1, int(request.args.get("page", 1) or 1))
            except (TypeError, ValueError):
                page = 1
            try:
                page_size = int(request.args.get("page_size", 20) or 20)
            except (TypeError, ValueError):
                page_size = 20
            page_size = min(100, max(10, page_size))
            all_items = metadata_items(PACKS_DIR / pack_id, request.args.get("status"))
            total = len(all_items)
            total_pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, total_pages)
            start = (page - 1) * page_size
            return jsonify(
                {
                    "pack_id": pack_id,
                    "items": all_items[start : start + page_size],
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                }
            ), 200
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取语义记录失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取语义记录失败"}), 500

    def _capture_item_time(item: dict, fallback: int = 0) -> int:
        for key in ("indexed_at", "captured_at", "last_duplicate_at"):
            try:
                value = int(item.get(key) or 0)
            except (TypeError, ValueError):
                value = 0
            if value:
                return value
        return fallback

    def _capture_workspace_for_pack(self, pack_id: str) -> dict:
        """Build the two-column capture view from catalogs, not browser state."""
        pack_dir = (PACKS_DIR / pack_id).resolve()
        store = MemeStore(pack_dir)
        activity = load_capture_activity(pack_dir)
        indexed_items: list[dict] = []
        pending_items: list[dict] = []
        folders: list[dict] = []

        for category in sorted(store.directory_categories()):
            paths = store.image_paths(category)
            catalog = store.load_catalog(category)
            catalog_items = [
                item for item in catalog.get("items", []) if isinstance(item, dict)
            ]
            by_filename = {
                str(item.get("filename")): item
                for item in catalog_items
                if item.get("filename")
            }
            indexed_count = 0
            category_pending: list[dict] = []
            category_indexed: list[dict] = []
            for path in paths:
                try:
                    digest = store.image_digest(path)
                    modified_at = int(path.stat().st_mtime)
                except OSError:
                    continue
                entry = dict(by_filename.get(path.name) or {})
                is_indexed = bool(entry.get("indexed"))
                item = {
                    **entry,
                    "category": category,
                    "filename": path.name,
                    "sha256": str(entry.get("sha256") or digest),
                    "relative_path": f"memes/{category}/{path.name}",
                    "indexed": is_indexed,
                    "captured_at": int(entry.get("captured_at") or modified_at),
                }
                if is_indexed:
                    indexed_count += 1
                    category_indexed.append(item)
                else:
                    item["activity_status"] = "pending"
                    category_pending.append(item)
            complete = bool(catalog.get("classification_index_complete")) and (
                indexed_count == len(paths)
            )
            folders.append(
                {
                    "category": category,
                    "total": len(paths),
                    "indexed": indexed_count,
                    "pending": len(category_pending),
                    "complete": complete,
                    "indexed_at": catalog.get("classification_indexed_at"),
                    "index_provider_id": catalog.get("index_provider_id", ""),
                }
            )
            indexed_items.extend(category_indexed)
            pending_items.extend(category_pending)

        duplicate_items: list[dict] = []
        duplicate_count = 0
        for event in activity.get("events", []):
            if not isinstance(event, dict) or event.get("status") != "duplicate":
                continue
            category = str(event.get("category") or "")
            filename = str(event.get("filename") or "")
            if not is_safe_category_segment(category) or not self._safe_image_filename(filename):
                continue
            path = store.memes_dir / category / filename
            if not path.is_file():
                continue
            duplicate_count += 1
            duplicate_items.append(
                {
                    "id": event.get("id", ""),
                    "category": category,
                    "filename": filename,
                    "sha256": event.get("sha256", ""),
                    "relative_path": f"memes/{category}/{filename}",
                    "indexed": False,
                    "duplicate": True,
                    "activity_status": "duplicate",
                    "duplicate_of": event.get("duplicate_of", ""),
                    "captured_at": event.get("captured_at", 0),
                }
            )
        pending_items.extend(duplicate_items)
        indexed_items.sort(key=lambda item: self._capture_item_time(item), reverse=True)
        pending_items.sort(key=lambda item: self._capture_item_time(item), reverse=True)

        state = dict(getattr(self, "_library_index_state", {}) or {})
        active_store = getattr(self, "store", None)
        state["active_pack"] = bool(
            active_store is not None
            and Path(getattr(active_store, "root", "")).resolve() == pack_dir
        )
        complete_folder_count = sum(1 for folder in folders if folder["complete"])
        return {
            "pack_id": pack_id,
            "library_index": state,
            "summary": {
                "indexed": len(indexed_items),
                "pending": len(pending_items) - duplicate_count,
                "duplicate": duplicate_count,
                "complete_folders": complete_folder_count,
                "folder_total": len(folders),
            },
            "folders": folders,
            "indexed_items": indexed_items[:48],
            "pending_items": pending_items[:48],
        }

    async def _api_semantic_capture_workspace(self):
        try:
            pack_id = await self._semantic_request_pack_id()
            return jsonify(self._capture_workspace_for_pack(pack_id)), 200
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取偷取表情包工作台失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取偷取表情包工作台失败"}), 500

    async def _api_semantic_capture_index(self):
        try:
            data = await request.get_json() or {}
            pack_id = await self._semantic_request_pack_id(data)
            pack_dir = (PACKS_DIR / pack_id).resolve()
            active_store = getattr(self, "store", None)
            if active_store is None or Path(active_store.root).resolve() != pack_dir:
                return jsonify({"message": "请先将该资源包设为当前运行资源包后再处理偷取索引"}), 409
            task = getattr(self, "_library_task", None)
            if task is not None and not task.done():
                return jsonify({"message": "分类索引正在处理中", "status": "running"}), 202
            self._library_completed_key = None
            self._library_retry_key = None
            self._library_retry_at = 0.0
            task = asyncio.create_task(self._ensure_library_index())
            self._library_task = task
            task.add_done_callback(self._log_library_task_failure)
            return jsonify({"message": "已开始处理待分类偷取表情包", "status": "running"}), 202
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("启动偷取表情包索引失败: %s", exc, exc_info=True)
            return jsonify({"message": "启动偷取表情包索引失败"}), 500

    async def _api_semantic_start(self):
        try:
            data = await request.get_json() or {}
            pack_id = await self._semantic_request_pack_id(data)
            external_data = (
                data.get("external_metadata")
                if isinstance(data.get("external_metadata"), dict)
                else None
            )
            external_path = data.get("external_metadata_path")
            if external_path:
                source = Path(str(external_path)).expanduser().resolve()
                allowed_roots = [PLUGIN_DATA_DIR.resolve(), TEMP_DIR.resolve()]
                if not any(
                    source == root or root in source.parents for root in allowed_roots
                ):
                    raise ValueError("外部语义文件必须位于插件数据目录或临时目录")
                external_data = import_metadata_file(source)
            result = await self.vector_semantic_service.start(
                pack_id,
                mode=str(data.get("mode") or "full"),
                force=bool(data.get("force", False)),
                concurrency=data.get("concurrency"),
                external_data=external_data,
            )
            return jsonify(result), 202
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("启动语义任务失败: %s", exc, exc_info=True)
            return jsonify({"message": "启动语义任务失败"}), 500

    async def _api_semantic_pause(self):
        return await self._api_semantic_task_action("pause")

    async def _api_semantic_resume(self):
        return await self._api_semantic_task_action("resume")

    async def _api_semantic_retry(self):
        try:
            data = await request.get_json() or {}
            pack_id = await self._semantic_request_pack_id(data)
            result = await self.vector_semantic_service.start(
                pack_id,
                mode="retry_failed",
                concurrency=data.get("concurrency"),
            )
            return jsonify(result), 202
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("重试语义任务失败: %s", exc, exc_info=True)
            return jsonify({"message": "重试语义任务失败"}), 500

    async def _api_semantic_task_action(self, action: str):
        try:
            data = await request.get_json() or {}
            pack_id = await self._semantic_request_pack_id(data)
            if action == "resume":
                result = await self.vector_semantic_service.resume(
                    pack_id, concurrency=data.get("concurrency")
                )
            else:
                result = await getattr(self.vector_semantic_service, action)(pack_id)
            return jsonify(result), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("语义任务操作失败: %s", exc, exc_info=True)
            return jsonify({"message": "语义任务操作失败"}), 500

    async def _api_semantic_rebuild_index(self):
        try:
            data = await request.get_json() or {}
            pack_id = await self._semantic_request_pack_id(data)
            result = await self.vector_semantic_service.rebuild_index(
                pack_id, force=bool(data.get("force", False))
            )
            return jsonify({"message": "向量索引已建立", **result}), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("重建语义索引失败: %s", exc, exc_info=True)
            return jsonify({"message": "重建语义索引失败"}), 500

    async def _api_semantic_clear_local_state(self):
        try:
            data = await request.get_json() or {}
            pack_id = await self._semantic_request_pack_id(data)
            result = await self.vector_semantic_service.clear_local_semantic_state(
                pack_id
            )
            return jsonify(
                {"message": "已清理本机任务与向量，图片描述已保留", **result}
            ), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("清理本机语义状态失败: %s", exc, exc_info=True)
            return jsonify({"message": "清理本机语义状态失败"}), 500

    async def _api_semantic_delete_all(self):
        try:
            data = await request.get_json() or {}
            pack_id = await self._semantic_request_pack_id(data)
            result = await self.vector_semantic_service.delete_all_semantic_data(pack_id)
            return jsonify(
                {
                    "message": "已删除当前资源包的全部语义化数据，原图片已保留",
                    **result,
                }
            ), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("删除全部语义化数据失败: %s", exc, exc_info=True)
            return jsonify({"message": "删除全部语义化数据失败"}), 500
