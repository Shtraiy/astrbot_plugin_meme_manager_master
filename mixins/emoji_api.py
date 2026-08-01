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




class EmojiAPIMixin:
    @staticmethod
    def _build_file_data_url(file_path: Path, mime_type: str) -> str:
        with file_path.open("rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _build_preview_data_url(file_path: Path) -> tuple[str, str]:
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

    @staticmethod
    def _safe_image_filename(value: str) -> bool:
        normalized = str(value or "").strip()
        return bool(
            normalized
            and normalized not in {".", ".."}
            and Path(normalized).name == normalized
            and "/" not in normalized
            and "\\" not in normalized
            and Path(normalized).suffix.lower() in IMAGE_EXTENSIONS
        )

    async def _api_get_emojis(self):
        view_context = self._resolve_webui_pack_view_context()
        if view_context:
            emoji_data = self._scan_pack_emojis(view_context["memes_dir"])
        else:
            emoji_data = await scan_emoji_folder()
        for category in emoji_data:
            if not isinstance(emoji_data[category], list):
                emoji_data[category] = []
        return jsonify(emoji_data)

    async def _api_get_emoji_by_category(self, category):
        view_context = self._resolve_webui_pack_view_context()
        if view_context:
            if not is_safe_category_segment(category):
                return jsonify({"message": "分类名无效"}), 400
            category_path = view_context["memes_dir"] / category
            if not category_path.is_dir():
                emojis = []
            else:
                emojis = [
                    file_path.name
                    for file_path in category_path.iterdir()
                    if file_path.is_file()
                    and file_path.suffix.lower()
                    in {
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".gif",
                        ".webp",
                    }
                ]
        else:
            emojis = get_emoji_by_category(category)
        if emojis is None:
            return jsonify({"message": "分类未找到"}), 404
        return jsonify(emojis if isinstance(emojis, list) else []), 200

    async def _api_add_emoji(self, category):
        try:
            files = await request.files
            if not files or "file" not in files:
                return jsonify({"message": "没有找到上传的图片文件"}), 400
            image_file = files["file"]
            if not image_file or not image_file.filename:
                return jsonify({"message": "无效的图片文件"}), 400
            logger.info(f"收到上传请求: 类别={category}, 文件名={image_file.filename}")
            try:

                def mutate():
                    add_result = add_emoji_to_category(category, image_file)
                    self.category_manager.sync_with_filesystem()
                    self._invalidate_default_pack_semantics()
                    return add_result

                result = await self._run_default_pack_mutation("上传表情图片", mutate)
                logger.info(f"表情添加成功: {result['path']}")
                return (
                    jsonify(
                        {
                            "message": "表情添加成功",
                            "path": result["path"],
                            "category": category,
                            "filename": result["filename"],
                        }
                    ),
                    201,
                )
            except DuplicateEmojiError as e:
                logger.info(f"跳过重复表情: {e}")
                return (
                    jsonify(
                        {
                            "message": str(e),
                            "code": "duplicate_emoji",
                            "category": category,
                            "filename": e.existing_filename,
                        }
                    ),
                    409,
                )
            except RuntimeError as e:
                return jsonify({"message": str(e)}), 409
        except Exception as e:
            logger.error(f"处理上传请求时出错: {e}", exc_info=True)
            return jsonify({"message": f"处理上传请求时出错: {str(e)}"}), 500

    async def _api_delete_emoji(self):
        data = await request.get_json()
        category = data.get("category")
        image_file = data.get("image_file")
        if not category or not image_file:
            return jsonify({"message": "分类和文件名不能为空"}), 400

        def mutate():
            deleted = delete_emoji_from_category(category, image_file)
            if deleted:
                self._invalidate_default_pack_semantics()
            return deleted

        try:
            deleted = await self._run_default_pack_mutation("删除表情图片", mutate)
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        if deleted:
            return (
                jsonify(
                    {
                        "message": "表情删除成功",
                        "category": category,
                        "filename": image_file,
                    }
                ),
                200,
            )
        return jsonify({"message": "表情未找到"}), 404

    async def _api_batch_delete_emojis(self):
        data = await request.get_json()
        category = data.get("category")
        image_files = data.get("image_files")
        if not category or not isinstance(image_files, list) or not image_files:
            return jsonify({"message": "分类和文件名列表不能为空"}), 400

        def mutate():
            delete_result = batch_delete_emojis(category, image_files)
            if delete_result.get("deleted_files"):
                self._invalidate_default_pack_semantics()
            return delete_result

        try:
            result = await self._run_default_pack_mutation("批量删除表情图片", mutate)
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        if not result["category_exists"]:
            return jsonify({"message": "分类未找到"}), 404
        return (
            jsonify(
                {
                    "message": "批量删除完成",
                    "category": category,
                    "deleted_files": result["deleted_files"],
                    "missing_files": result["missing_files"],
                    "deleted_count": len(result["deleted_files"]),
                    "missing_count": len(result["missing_files"]),
                }
            ),
            200,
        )

    async def _api_move_emoji(self):
        data = await request.get_json()
        source_category = data.get("source_category")
        target_category = data.get("target_category")
        image_file = data.get("image_file")
        if not source_category or not target_category or not image_file:
            return jsonify({"message": "源分类、目标分类和文件名不能为空"}), 400
        if source_category == target_category:
            return jsonify({"message": "源分类和目标分类不能相同"}), 400

        def mutate():
            move_result = move_emoji_to_category(
                source_category, image_file, target_category
            )
            if move_result.get("moved"):
                self._invalidate_default_pack_semantics()
            return move_result

        try:
            result = await self._run_default_pack_mutation("移动表情图片", mutate)
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        if not result["source_category_exists"]:
            return jsonify({"message": "源分类未找到"}), 404
        if result["conflict"]:
            return jsonify({"message": "目标文件已存在"}), 409
        if result["missing"]:
            return jsonify({"message": "表情未找到"}), 404
        return (
            jsonify(
                {
                    "message": "表情移动成功",
                    "source_category": result["source_category"],
                    "target_category": result["target_category"],
                    "filename": result["filename"],
                }
            ),
            200,
        )

    async def _api_batch_move_emojis(self):
        data = await request.get_json()
        source_category = data.get("source_category")
        target_category = data.get("target_category")
        image_files = data.get("image_files")
        if (
            not source_category
            or not target_category
            or not isinstance(image_files, list)
            or not image_files
        ):
            return jsonify({"message": "源分类、目标分类和文件名列表不能为空"}), 400
        if source_category == target_category:
            return jsonify({"message": "源分类和目标分类不能相同"}), 400

        def mutate():
            move_result = batch_move_emojis(
                source_category, image_files, target_category
            )
            if move_result.get("moved_files"):
                self._invalidate_default_pack_semantics()
            return move_result

        try:
            result = await self._run_default_pack_mutation("批量移动表情图片", mutate)
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        if not result["source_category_exists"]:
            return jsonify({"message": "源分类未找到"}), 404
        return (
            jsonify(
                {
                    "message": "批量移动完成",
                    "source_category": source_category,
                    "target_category": target_category,
                    "moved_files": result["moved_files"],
                    "missing_files": result["missing_files"],
                    "conflicting_files": result["conflicting_files"],
                    "moved_count": len(result["moved_files"]),
                    "missing_count": len(result["missing_files"]),
                    "conflict_count": len(result["conflicting_files"]),
                }
            ),
            200,
        )

    async def _api_batch_copy_emojis(self):
        data = await request.get_json()
        source_category = data.get("source_category")
        target_category = data.get("target_category")
        image_files = data.get("image_files")
        if (
            not source_category
            or not target_category
            or not isinstance(image_files, list)
            or not image_files
        ):
            return jsonify({"message": "源分类、目标分类和文件名列表不能为空"}), 400

        def mutate():
            copy_result = batch_copy_emojis(
                source_category, image_files, target_category
            )
            if copy_result.get("copied_files"):
                self._invalidate_default_pack_semantics()
            return copy_result

        try:
            result = await self._run_default_pack_mutation("批量复制表情图片", mutate)
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        if not result["source_category_exists"]:
            return jsonify({"message": "源分类未找到"}), 404
        return (
            jsonify(
                {
                    "message": "批量复制完成",
                    "source_category": source_category,
                    "target_category": target_category,
                    "copied_files": result["copied_files"],
                    "missing_files": result["missing_files"],
                    "conflicting_files": result["conflicting_files"],
                    "copied_count": len(result["copied_files"]),
                    "missing_count": len(result["missing_files"]),
                    "conflict_count": len(result["conflicting_files"]),
                }
            ),
            200,
        )

    async def _api_clear_all_emojis(self):
        def mutate():
            clear_result = clear_all_emojis()
            if any(clear_result.get("deleted_by_category", {}).values()):
                self._invalidate_default_pack_semantics()
            return clear_result

        try:
            result = await self._run_default_pack_mutation("清空全部表情图片", mutate)
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        deleted_count = sum(result["deleted_by_category"].values())
        return (
            jsonify(
                {
                    "message": "所有表情已清空",
                    "deleted_by_category": result["deleted_by_category"],
                    "deleted_count": deleted_count,
                    "affected_categories": len(result["deleted_by_category"]),
                }
            ),
            200,
        )

    async def _api_get_emotions(self):
        try:
            view_context = self._resolve_webui_pack_view_context()
            if view_context:
                descriptions = self._load_pack_descriptions(view_context)
            else:
                descriptions = self.category_manager.get_descriptions()
            return jsonify(descriptions)
        except Exception as e:
            logger.error(f"获取标签描述失败: {e}")
            return jsonify({"error": "获取标签描述失败"}), 500

    async def _api_delete_category(self):
        try:
            data = await request.get_json()
            category = data.get("category")
            if not category:
                return jsonify({"message": "分类不能为空"}), 400
            deleted = await self._run_default_pack_mutation(
                "删除表情分类",
                lambda: self.category_manager.delete_category(category),
            )
            if deleted:
                return jsonify({"message": "分类删除成功"}), 200
            return jsonify({"message": "分类删除失败"}), 500
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except Exception as e:
            return jsonify({"message": f"分类删除失败: {str(e)}"}), 500

    async def _api_clear_category(self):
        data = await request.get_json()
        category = data.get("category")
        if not category:
            return jsonify({"message": "分类不能为空"}), 400

        def mutate():
            clear_result = clear_category_emojis(category)
            if clear_result.get("deleted_files"):
                self._invalidate_default_pack_semantics()
            return clear_result

        try:
            result = await self._run_default_pack_mutation("清空表情分类", mutate)
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        if not result["category_exists"]:
            return jsonify({"message": "分类未找到"}), 404
        return (
            jsonify(
                {
                    "message": "分类表情已清空",
                    "category": category,
                    "deleted_files": result["deleted_files"],
                    "deleted_count": len(result["deleted_files"]),
                }
            ),
            200,
        )

    async def _api_restore_category(self):
        try:
            data = await request.get_json()
            category = data.get("category")
            description = data.get("description", "请添加描述")
            if not category:
                return jsonify({"message": "分类不能为空"}), 400
            created = await self._run_default_pack_mutation(
                "创建表情分类",
                lambda: self.category_manager.create_category(category, description),
            )
            if created:
                return (
                    jsonify({"message": "分类创建成功", "description": description}),
                    200,
                )
            return jsonify({"message": "分类创建失败"}), 500
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except Exception as e:
            return jsonify({"message": f"分类创建失败: {str(e)}"}), 500

    async def _api_rename_category(self):
        try:
            data = await request.get_json()
            old_name = data.get("old_name")
            new_name = data.get("new_name")
            if not old_name or not new_name:
                return jsonify({"message": "旧分类名和新分类名不能为空"}), 400
            renamed = await self._run_default_pack_mutation(
                "重命名表情分类",
                lambda: self.category_manager.rename_category(old_name, new_name),
            )
            if renamed:
                return jsonify({"message": "分类重命名成功"}), 200
            return jsonify({"message": "分类重命名失败"}), 500
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except Exception as e:
            return jsonify({"message": f"分类重命名失败: {str(e)}"}), 500

    async def _api_update_description(self):
        try:
            data = await request.get_json()
            category = data.get("tag")
            description = data.get("description")
            if not category or not description:
                return jsonify({"message": "分类和描述不能为空"}), 400
            updated = await self._run_default_pack_mutation(
                "更新表情分类描述",
                lambda: self.category_manager.update_description(category, description),
            )
            if updated:
                return jsonify({"category": category, "description": description}), 200
            return jsonify({"message": "更新分类描述失败"}), 500
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except Exception as e:
            return jsonify({"message": f"更新分类描述失败: {str(e)}"}), 500

    async def _api_remove_from_config(self):
        try:
            data = await request.get_json()
            category = data.get("category")
            if not category:
                return jsonify({"message": "分类不能为空"}), 400
            removed = await self._run_default_pack_mutation(
                "移除表情分类配置",
                lambda: self.category_manager.remove_from_config(category),
            )
            if removed:
                return jsonify({"message": "已从配置中移除分类"}), 200
            return jsonify({"message": "从配置中移除分类失败"}), 500
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except Exception as e:
            return jsonify({"message": f"从配置中移除分类失败: {str(e)}"}), 500

    async def _api_sync_status(self):
        try:
            missing_in_config, deleted_categories = (
                self.category_manager.get_sync_status()
            )
            return jsonify(
                {
                    "status": "ok",
                    "missing_in_config": missing_in_config,
                    "deleted_categories": deleted_categories,
                    "differences": {
                        "missing_in_config": missing_in_config,
                        "deleted_categories": deleted_categories,
                    },
                }
            )
        except Exception as e:
            logger.error(f"获取同步状态失败: {e}")
            return jsonify({"error": "获取同步状态失败"}), 500

    async def _api_sync_config(self):
        try:
            logger.info("开始同步配置...")
            synced = await self._run_default_pack_mutation(
                "同步表情分类配置",
                self.category_manager.sync_with_filesystem,
            )
            if synced:
                logger.info("配置同步成功")
                return jsonify({"message": "配置同步成功"}), 200
            logger.warning("配置同步失败")
            return jsonify({"message": "配置同步失败"}), 500
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except Exception as e:
            logger.error(f"配置同步失败: {e}")
            return jsonify({"message": f"配置同步失败: {str(e)}"}), 500

    async def _api_serve_meme_image(self):
        category = str(request.args.get("category", "") or "").strip()
        filename = str(request.args.get("filename", "") or "").strip()
        if not is_safe_category_segment(category) or not self._safe_image_filename(filename):
            return jsonify({"status": "error", "message": "分类或文件名无效"}), 400
        view_context = self._resolve_webui_pack_view_context()
        memes_root = (
            view_context["memes_dir"].resolve()
            if view_context
            else Path(self._default_pack_context()["memes_dir"]).resolve()
        )
        file_path = (memes_root / category / filename).resolve()
        try:
            file_path.relative_to(memes_root)
        except ValueError:
            return jsonify({"status": "error", "message": "非法路径"}), 403
        if not file_path.is_file():
            return jsonify({"status": "error", "message": "文件不存在"}), 404
        return await send_file(str(file_path))

    async def _api_get_meme_image_data(self):
        category = str(request.args.get("category", "") or "").strip()
        filename = str(request.args.get("filename", "") or "").strip()
        size = request.args.get("size", "preview")
        if not is_safe_category_segment(category) or not self._safe_image_filename(filename):
            return jsonify({"status": "error", "message": "分类或文件名无效"}), 400
        view_context = self._resolve_webui_pack_view_context()
        memes_root = (
            view_context["memes_dir"].resolve()
            if view_context
            else Path(self._default_pack_context()["memes_dir"]).resolve()
        )
        file_path = (memes_root / category / filename).resolve()

        try:
            file_path.relative_to(memes_root)
        except ValueError:
            return jsonify({"status": "error", "message": "Invalid path"}), 403

        if not file_path.exists() or not file_path.is_file():
            return jsonify({"status": "error", "message": "File not found"}), 404

        file_size = file_path.stat().st_size
        mime_type = (
            mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        )
        preview_mode = image_preview_mode(
            file_size=file_size,
            mime_type=mime_type,
            requested_size=size,
            raw_preview_limit=MAX_PREVIEW_IMAGE_BYTES,
            source_limit=MAX_ORIGINAL_IMAGE_BYTES,
        )
        if preview_mode == "reject":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Image is too large to preview in the plugin page",
                        "size": file_size,
                        "max_size": MAX_ORIGINAL_IMAGE_BYTES,
                    }
                ),
                413,
            )

        if preview_mode == "thumbnail":
            try:
                data_url, mime_type = self._build_preview_data_url(file_path)
            except Exception as exc:
                if file_size > MAX_PREVIEW_IMAGE_BYTES:
                    logger.warning(f"生成大图预览缩略图失败: {exc}")
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "无法生成图片预览",
                                "size": file_size,
                            }
                        ),
                        422,
                    )
                logger.warning(f"生成预览缩略图失败，回退原图数据: {exc}")
                data_url = self._build_file_data_url(file_path, mime_type)
        else:
            data_url = self._build_file_data_url(file_path, mime_type)

        return jsonify(
            {
                "category": category,
                "filename": filename,
                "mime_type": mime_type,
                "size": file_size,
                "data_url": data_url,
            }
        )
