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
from ..storage import (
    IMAGE_EXTENSIONS,
    MemeStore,
    image_preview_mode,
    is_safe_category_segment,
    scan_pack_emojis,
)
from .web_routes import enabled_route_specs
from .emoji_api import EmojiAPIMixin
from .pack_api import PackAPIMixin
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



class WebAPIMixin(EmojiAPIMixin, PackAPIMixin):
    def _get_github_accelerator_url(self) -> str:
        value = self._read_config_value(
            ("community", "github_accelerator_url"),
            default="https://ghfast.top/",
            legacy_keys=("github_accelerator_url",),
        )
        return str(value or "").strip()

    def _register_web_apis(self):
        # ?????????????????????????????
        for spec in enabled_route_specs(self.web_capabilities):
            self._register_webui_api(
                spec.path,
                getattr(self, spec.handler_name),
                list(spec.methods),
                spec.description,
            )

    def _register_webui_api(self, route, handler, methods, desc):
        route_path = f"/{PLUGIN_NAME}/{route.strip('/')}"

        async def logged_handler(*args, **kwargs):
            started_at = time.monotonic()
            try:
                response = await handler(*args, **kwargs)
            except Exception:
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                logger.error(
                    f"{WEBUI_LOG_PREFIX} {request.method} {route_path} 失败 耗时={elapsed_ms}ms",
                    exc_info=True,
                )
                raise
            return response

        logged_handler.__name__ = f"webui_{handler.__name__}"
        self.context.register_web_api(route_path, logged_handler, methods, desc)

    def _get_webui_response_status(response) -> int | str:
        if isinstance(response, tuple) and len(response) > 1:
            return response[1]
        return getattr(response, "status_code", "unknown")

    def _semantic_operation_guard(self, pack_id: str, operation: str) -> None:
        self.catalog_index_service.assert_pack_mutation_allowed(pack_id, operation)

    def _semantic_rebuild_guidance(self, pack_id: str) -> dict:
        return {}
        """返回切换或导入资源包后是否需要补建本机向量。"""
        guidance = {
            "semantic_rebuild_required": False,
            "semantic_rebuild_pack_id": str(pack_id or "").strip(),
        }
        if not guidance["semantic_rebuild_pack_id"] or not bool(
            getattr(self, "semantic_enabled", False)
        ):
            return guidance
        manager = getattr(self, "semantic_task_manager", None)
        if manager is None:
            return guidance
        try:
            status = manager.status(guidance["semantic_rebuild_pack_id"])
        except Exception as exc:
            logger.warning(
                "读取资源包向量重建提示失败: %s | pack_id=%s",
                exc,
                guidance["semantic_rebuild_pack_id"],
            )
            return guidance
        task_status = str(status.get("task_status") or "")
        guidance.update(
            {
                "semantic_rebuild_required": bool(
                    status.get("dimension_rebuild_required")
                    and status.get("semantic_caption_complete")
                    and task_status not in {"running", "paused"}
                ),
                "semantic_task_status": task_status,
                "semantic_caption_complete": bool(
                    status.get("semantic_caption_complete")
                ),
                "semantic_index_ready": bool(status.get("index_ready")),
                "semantic_embedding_provider_id": str(
                    status.get("embedding_provider_id") or ""
                ),
                "semantic_embedding_model": str(status.get("embedding_model") or ""),
                "semantic_embedding_dimension": int(
                    status.get("embedding_configured_dimension", 0) or 0
                ),
            }
        )
        return guidance

    def _pack_import_embedding_signature(self) -> dict:
        return {}
        """Return the active local embedding signature for safe backup restore."""
        try:
            provider = self._resolve_embedding_provider()
            embedding = EmbeddingAdapter(
                provider, str(getattr(self, "semantic_embedding_provider_id", "") or "")
            )
        except Exception:
            return {
                "embedding_provider_id": "",
                "embedding_model": "",
                "embedding_dimension": 0,
            }
        if not embedding.ready:
            return {
                "embedding_provider_id": "",
                "embedding_model": "",
                "embedding_dimension": 0,
            }
        return {
            "embedding_provider_id": embedding.provider_id,
            "embedding_model": embedding.model_name,
            "embedding_dimension": embedding.dimension,
        }

    async def _run_guarded_pack_file_operation(
        self,
        pack_id: str,
        operation: str,
        function,
        *args,
        **kwargs,
    ):
        """在整个文件快照期间阻止同一表情包的目录索引变更。"""
        guard = self.catalog_index_service
        locked = False
        if pack_id:
            guard.begin_external_pack_operation(pack_id, operation)
            locked = True
        kwargs["operation_guard"] = None if locked else self._semantic_operation_guard
        worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(worker)
            except Exception:
                pass
            raise
        finally:
            if locked:
                guard.end_external_pack_operation(pack_id)

    async def _run_guarded_runtime_file_operation(
        self,
        operation: str,
        function,
        *args,
        **kwargs,
    ):
        """Hold every installed pack lock for one runtime-wide file operation."""
        guard = self.catalog_index_service
        pack_ids = (
            sorted(path.name for path in PACKS_DIR.iterdir() if path.is_dir())
            if PACKS_DIR.is_dir()
            else []
        )
        locked_pack_ids = []
        try:
            for pack_id in pack_ids:
                guard.begin_external_pack_operation(pack_id, operation)
                locked_pack_ids.append(pack_id)
        except Exception:
            for pack_id in reversed(locked_pack_ids):
                guard.end_external_pack_operation(pack_id)
            raise

        kwargs["operation_guard"] = None
        worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(worker)
            except Exception:
                pass
            raise
        finally:
            for pack_id in reversed(locked_pack_ids):
                guard.end_external_pack_operation(pack_id)

    def _prepare_archive_upload_request() -> None:
        """覆盖 Quart 兼容层默认的 16 MB 请求上限。"""
        try:
            request.max_content_length = MAX_PACK_UPLOAD_REQUEST_BYTES
        except (AttributeError, RuntimeError):
            # 新版 AstrBot 使用 Starlette 上传对象，不需要在这里调整限制。
            pass

    async def _save_uploaded_file(uploaded_file, destination: Path) -> None:
        """同时兼容 Quart 的异步 save 与旧版同步 save。"""
        save_method = uploaded_file.save
        if inspect.iscoroutinefunction(save_method):
            await save_method(str(destination))
            return
        result = await asyncio.to_thread(save_method, str(destination))
        if inspect.isawaitable(result):
            await result

    def _pack_import_session_paths(token: str) -> tuple[Path, Path]:
        normalized = str(token or "").strip().lower()
        if len(normalized) != 32 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("导入凭证无效，请重新选择压缩包")
        session_dir = TEMP_DIR / "pack_import_sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / f"{normalized}.zip", session_dir / f"{normalized}.json"

    def _cleanup_pack_import_sessions() -> None:
        session_dir = TEMP_DIR / "pack_import_sessions"
        if not session_dir.is_dir():
            return
        expire_before = time.time() - PACK_IMPORT_SESSION_TTL_SECONDS
        for path in session_dir.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < expire_before:
                    path.unlink()
            except OSError:
                continue

    def _guard_default_pack_file_operation(self, operation: str):
        pack_id = str(self._default_pack_context()["pack_id"] or "").strip()
        try:
            if pack_id:
                self._semantic_operation_guard(pack_id, operation)
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        return None

    async def _run_default_pack_mutation(self, operation: str, mutation):
        """让分类/移动操作与目录索引变更共享同一把包锁。"""
        pack_id = str(self._default_pack_context()["pack_id"] or "").strip()
        if not pack_id:
            result = mutation()
        else:
            result = await self.catalog_index_service.run_locked_pack_mutation(
                pack_id, operation, mutation
            )
        return result

    def _default_pack_context() -> dict[str, Path | str]:
        try:
            return get_active_pack_paths()
        except Exception:
            return {
                "pack_id": MEMES_DIR.parent.name,
                "pack_dir": MEMES_DIR.resolve().parent,
                "memes_dir": MEMES_DIR.resolve(),
            }

    def _invalidate_default_pack_semantics(self) -> None:
        return
        pack_dir = Path(self._default_pack_context()["pack_dir"]).resolve()
        if not (pack_dir / "semantic_metadata.json").is_file():
            return
        try:
            invalidate_semantic_metadata(pack_dir)
        except Exception as exc:
            logger.error("图片变更后刷新语义元数据失败: %s", exc, exc_info=True)

    def _resolve_webui_pack_view_context(self) -> dict | None:
        managed_pack_id = str(request.args.get("managed_pack_id") or "").strip()
        if not managed_pack_id:
            return None
        if not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", managed_pack_id):
            return None

        pack_dir = (PACKS_DIR / managed_pack_id).resolve()
        packs_root = PACKS_DIR.resolve()
        try:
            pack_dir.relative_to(packs_root)
        except ValueError:
            return None
        if not pack_dir.is_dir():
            return None

        return {
            "pack_id": managed_pack_id,
            "pack_dir": pack_dir,
            "memes_dir": pack_dir / "memes",
            "memes_data_path": pack_dir / "memes_data.json",
            "manifest_path": pack_dir / "manifest.json",
        }

    def _scan_pack_emojis(memes_dir: Path) -> dict:
        return scan_pack_emojis(memes_dir)

    def _load_pack_descriptions(view_context: dict) -> dict:
        descriptions = {}
        memes_data_path = view_context["memes_data_path"]
        if memes_data_path.is_file():
            try:
                with memes_data_path.open(encoding="utf-8-sig") as file_obj:
                    data = json.load(file_obj)
                if isinstance(data, dict):
                    descriptions.update(
                        {
                            str(key): str(value)
                            for key, value in data.items()
                            if str(key).strip()
                        }
                    )
            except Exception:
                pass

        manifest_path = view_context["manifest_path"]
        if manifest_path.is_file():
            try:
                with manifest_path.open(encoding="utf-8-sig") as file_obj:
                    manifest = json.load(file_obj)
                categories = (
                    manifest.get("categories", {}) if isinstance(manifest, dict) else {}
                )
                if isinstance(categories, dict):
                    for category_name, category_meta in categories.items():
                        key = str(category_name or "").strip()
                        if not key or key in descriptions:
                            continue
                        if isinstance(category_meta, dict):
                            descriptions[key] = str(
                                category_meta.get("description") or "请添加描述"
                            )
                        else:
                            descriptions[key] = str(category_meta or "请添加描述")
            except Exception:
                pass

        return descriptions
