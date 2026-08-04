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


def _decode_bounded_base64(value: str, limit: int) -> bytes:
    """Decode Base64 only when both encoded and decoded sizes fit the limit."""
    encoded = str(value or "").strip()
    if not encoded:
        raise ValueError("file_b64 不能为空")
    max_encoded_chars = ((int(limit) + 2) // 3) * 4
    if len(encoded) > max_encoded_chars:
        raise ValueError("备份文件超过 1 GB，无法通过 WebUI 导入")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("file_b64 非法") from exc
    if len(decoded) > int(limit):
        raise ValueError("备份文件超过 1 GB，无法通过 WebUI 导入")
    return decoded


def _public_export_result(result: dict | None) -> dict:
    """Remove local filesystem paths before an export result reaches WebUI."""
    payload = dict(result or {})
    archive_path = payload.pop("archive_path", None)
    if archive_path and not payload.get("archive_filename"):
        payload["archive_filename"] = Path(str(archive_path)).name
    return payload




class PackAPIMixin:
    def _pack_runtime(self):
        """Return the application runtime service when the composition root provides it.

        The fallback keeps standalone mixin users and older integrations working while
        allowing normal plugin requests to cross the application boundary.
        """
        return getattr(self, "pack_runtime_service", None)

    async def _api_list_packs(self):
        try:
            service = self._pack_runtime()
            packs = service.list() if service is not None else list_installed_packs()
            return jsonify({"packs": packs})
        except Exception as e:
            logger.error(f"获取已安装表情包列表失败: {e}", exc_info=True)
            return jsonify({"message": f"获取已安装表情包列表失败: {str(e)}"}), 500

    async def _api_get_pack_detail(self, pack_id: str):
        try:
            service = self._pack_runtime()
            result = service.detail(pack_id) if service is not None else get_pack_detail(pack_id)
            return jsonify(result)
        except FileNotFoundError as e:
            return jsonify({"message": str(e)}), 404
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except ValueError as e:
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"获取表情包详情失败: {e}", exc_info=True)
            return jsonify({"message": f"获取表情包详情失败: {str(e)}"}), 500

    async def _api_set_default_pack(self):
        try:
            data = await request.get_json()
            pack_id = str((data or {}).get("pack_id") or "").strip()
            if not pack_id:
                return jsonify({"message": "pack_id 不能为空"}), 400
            service = self._pack_runtime()
            result = service.set_default(pack_id) if service is not None else set_default_pack(pack_id)
            refresh_store = getattr(self, "_refresh_store_for_active_pack", None)
            if callable(refresh_store):
                refresh_store()
            self._reload_personas()
            return jsonify({"message": "默认表情包设置成功", **result}), 200
        except FileNotFoundError as e:
            return jsonify({"message": str(e)}), 404
        except ValueError as e:
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"设置默认表情包失败: {e}", exc_info=True)
            return jsonify({"message": f"设置默认表情包失败: {str(e)}"}), 500

    async def _api_export_pack(self):
        try:
            data = await request.get_json()
            payload = data or {}
            pack_id = str(payload.get("pack_id") or "").strip()
            output_dir = payload.get("output_dir")
            export_mode = str(payload.get("export_mode") or "share").strip().lower()
            transfer = getattr(self, "pack_transfer_service", None)
            export_operation = transfer.export if transfer is not None else export_pack_archive
            result = await self._run_guarded_pack_file_operation(
                pack_id,
                "导出资源包",
                export_operation,
                pack_id,
                output_dir=output_dir,
                include_semantic=False,
                export_mode=export_mode,
            )
            return jsonify({"message": "导出成功", **_public_export_result(result)}), 200
        except FileNotFoundError as e:
            return jsonify({"message": str(e)}), 404
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except ValueError as e:
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"导出表情包失败: {e}", exc_info=True)
            return jsonify({"message": f"导出表情包失败: {str(e)}"}), 500

    async def _api_pack_export_status(self):
        try:
            pack_id = str(request.args.get("pack_id") or "").strip()
            result = await asyncio.to_thread(get_pack_export_capabilities, pack_id)
            return jsonify(result), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取表情包导出能力失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取表情包导出能力失败"}), 500

    async def _api_download_pack(self):
        try:
            pack_id = str(request.args.get("pack_id") or "").strip()
            export_mode = str(request.args.get("mode") or "share").strip().lower()
            transfer = getattr(self, "pack_transfer_service", None)
            export_operation = transfer.export if transfer is not None else export_pack_archive
            result = await self._run_guarded_pack_file_operation(
                pack_id,
                "导出资源包",
                export_operation,
                pack_id,
                export_mode=export_mode,
            )
            return await send_file(
                result["archive_path"],
                mimetype="application/zip",
                as_attachment=True,
                attachment_filename=result["archive_filename"],
            )
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("下载表情包失败: %s", exc, exc_info=True)
            return jsonify({"message": "下载表情包失败"}), 500

    async def _api_import_pack(self):
        temp_zip_path = None
        try:
            self._prepare_archive_upload_request()
            content_length = request.content_length
            if (
                content_length is not None
                and content_length > MAX_PACK_UPLOAD_REQUEST_BYTES
            ):
                return jsonify({"message": "压缩包超过 1 GB，无法通过 WebUI 导入"}), 413
            form = await request.form
            overwrite = str(form.get("overwrite", "false")).lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            set_as_default = str(form.get("set_as_default", "false")).lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            files = await request.files
            if not files or "file" not in files:
                return jsonify({"message": "缺少上传文件字段 file"}), 400

            archive_file = files["file"]
            if not archive_file or not archive_file.filename:
                return jsonify({"message": "无效的压缩包文件"}), 400

            filename = str(archive_file.filename)
            if not filename.lower().endswith(".zip"):
                return jsonify({"message": "仅支持 zip 压缩包"}), 400

            temp_dir = TEMP_DIR
            temp_dir.mkdir(parents=True, exist_ok=True)
            safe_name = f"import_{int(time.time() * 1000)}.zip"
            temp_zip_path = (temp_dir / safe_name).resolve()
            await self._save_uploaded_file(archive_file, temp_zip_path)

            suggested_pack_id = Path(filename).stem
            transfer = getattr(self, "pack_transfer_service", None)
            import_operation = transfer.import_pack if transfer is not None else import_pack_archive
            if overwrite:
                inspection = await asyncio.to_thread(
                    inspect_pack_archive,
                    temp_zip_path,
                    suggested_pack_id=suggested_pack_id,
                )
                result = await self._run_guarded_pack_file_operation(
                    str(inspection.get("pack_id") or ""),
                    "覆盖安装资源包",
                    import_operation,
                    temp_zip_path,
                    overwrite=True,
                    set_as_default=set_as_default,
                    suggested_pack_id=suggested_pack_id,
                    preserve_existing_manual=False,
                )
            else:
                result = await self._run_guarded_runtime_file_operation(
                    "安装资源包",
                    import_operation,
                    temp_zip_path,
                    overwrite=False,
                    set_as_default=set_as_default,
                    suggested_pack_id=suggested_pack_id,
                    preserve_existing_manual=False,
                )
            self._reload_personas()
            return jsonify({"message": "导入成功", **result}), 200
        except FileExistsError as e:
            return jsonify({"message": str(e)}), 409
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except RequestEntityTooLarge:
            return jsonify({"message": "压缩包超过 1 GB，无法通过 WebUI 导入"}), 413
        except (FileNotFoundError, ValueError) as e:
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"导入表情包失败: {e}", exc_info=True)
            return jsonify({"message": f"导入表情包失败: {str(e)}"}), 500
        finally:
            if temp_zip_path and temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                except Exception:
                    pass

    async def _api_stage_pack_import(self):
        archive_path = None
        metadata_path = None
        try:
            self._prepare_archive_upload_request()
            self._cleanup_pack_import_sessions()
            content_length = request.content_length
            if (
                content_length is not None
                and content_length > MAX_PACK_UPLOAD_REQUEST_BYTES
            ):
                return jsonify({"message": "压缩包超过 1 GB，无法通过 WebUI 导入"}), 413
            files = await request.files
            if not files or "file" not in files:
                return jsonify({"message": "缺少上传文件字段 file"}), 400
            archive_file = files["file"]
            filename = str(getattr(archive_file, "filename", "") or "").strip()
            if not filename or not filename.lower().endswith(".zip"):
                return jsonify({"message": "请选择 zip 格式的表情包"}), 400

            token = secrets.token_hex(16)
            archive_path, metadata_path = self._pack_import_session_paths(token)
            await self._save_uploaded_file(archive_file, archive_path)
            if archive_path.stat().st_size > MAX_PACK_ARCHIVE_BYTES:
                raise ValueError("压缩包超过 1 GB，无法通过 WebUI 导入")

            suggested_pack_id = Path(filename).stem
            inspection = await asyncio.to_thread(
                inspect_pack_archive,
                archive_path,
                suggested_pack_id=suggested_pack_id,
            )
            metadata_path.write_text(
                json.dumps(
                    {
                        "filename": filename,
                        "suggested_pack_id": suggested_pack_id,
                        "pack_id": str(inspection.get("pack_id") or ""),
                        "created_at": time.time(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return jsonify(
                {
                    "message": "压缩包检查完成，请确认后导入",
                    "import_token": token,
                    **inspection,
                }
            ), 200
        except (FileNotFoundError, ValueError, zipfile.BadZipFile) as exc:
            for path in (archive_path, metadata_path):
                if path and path.exists():
                    path.unlink()
            return jsonify({"message": str(exc)}), 400
        except RequestEntityTooLarge:
            for path in (archive_path, metadata_path):
                if path and path.exists():
                    path.unlink()
            return jsonify({"message": "压缩包超过 1 GB，无法通过 WebUI 导入"}), 413
        except Exception as exc:
            for path in (archive_path, metadata_path):
                if path and path.exists():
                    path.unlink()
            logger.error("预检导入压缩包失败: %s", exc, exc_info=True)
            return jsonify({"message": "预检导入压缩包失败"}), 500

    async def _api_apply_pack_import(self):
        try:
            self._cleanup_pack_import_sessions()
            data = await request.get_json() or {}
            token = str(data.get("import_token") or "").strip()
            archive_path, metadata_path = self._pack_import_session_paths(token)
            if not archive_path.is_file() or not metadata_path.is_file():
                raise ValueError("导入凭证已过期，请重新选择压缩包")
            session_data = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(session_data, dict):
                raise ValueError("导入凭证损坏，请重新选择压缩包")

            overwrite = str(data.get("overwrite", "false")).lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            set_as_default = str(data.get("set_as_default", "false")).lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            import_kwargs = {
                "overwrite": overwrite,
                "set_as_default": set_as_default,
                "suggested_pack_id": str(session_data.get("suggested_pack_id") or ""),
                "preserve_existing_manual": False,
            }
            transfer = getattr(self, "pack_transfer_service", None)
            import_operation = transfer.import_pack if transfer is not None else import_pack_archive
            if overwrite:
                result = await self._run_guarded_pack_file_operation(
                    str(session_data.get("pack_id") or ""),
                    "覆盖安装资源包",
                    import_operation,
                    archive_path,
                    **import_kwargs,
                )
            else:
                result = await self._run_guarded_runtime_file_operation(
                    "安装资源包",
                    import_operation,
                    archive_path,
                    **import_kwargs,
                )
            archive_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            self._reload_personas()
            return jsonify({"message": "表情包导入成功", **result}), 200
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except FileExistsError as exc:
            return jsonify({"message": str(exc)}), 409
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("确认导入表情包失败: %s", exc, exc_info=True)
            return jsonify({"message": "确认导入表情包失败"}), 500

    async def _api_uninstall_pack(self):
        try:
            data = await request.get_json()
            pack_id = str((data or {}).get("pack_id") or "").strip()
            if not pack_id:
                return jsonify({"message": "pack_id 不能为空"}), 400
            transfer = getattr(self, "pack_transfer_service", None)
            uninstall_operation = transfer.uninstall if transfer is not None else uninstall_pack
            result = await self._run_guarded_pack_file_operation(
                pack_id,
                "卸载资源包",
                uninstall_operation,
                pack_id,
            )
            self._reload_personas()
            return jsonify({"message": "卸载成功", **result}), 200
        except FileNotFoundError as e:
            return jsonify({"message": str(e)}), 404
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except ValueError as e:
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"卸载表情包失败: {e}", exc_info=True)
            return jsonify({"message": f"卸载表情包失败: {str(e)}"}), 500

    async def _api_fetch_community_index(self):
        try:
            index_url = COMMUNITY_INDEX_URL
            cache_data = fetch_and_cache_community_index(
                index_url,
                github_accelerator_url=self._get_github_accelerator_url(),
            )
            packs = cache_data.get("index", {}).get("packs", [])
            return (
                jsonify(
                    {
                        "message": "社区索引拉取成功",
                        "fetched_at": cache_data.get("fetched_at"),
                        "source_url": cache_data.get("source_url"),
                        "pack_count": len(packs) if isinstance(packs, list) else 0,
                        "index": cache_data.get("index", {}),
                    }
                ),
                200,
            )
        except ValueError as e:
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"拉取社区索引失败: {e}", exc_info=True)
            return jsonify({"message": f"拉取社区索引失败: {str(e)}"}), 500

    async def _api_get_cached_community_index(self):
        try:
            cache_data = load_cached_community_index()
            packs = cache_data.get("index", {}).get("packs", [])
            return (
                jsonify(
                    {
                        "fetched_at": cache_data.get("fetched_at"),
                        "source_url": cache_data.get("source_url"),
                        "pack_count": len(packs) if isinstance(packs, list) else 0,
                        "index": cache_data.get("index", {}),
                    }
                ),
                200,
            )
        except FileNotFoundError as e:
            return jsonify({"message": str(e)}), 404
        except ValueError as e:
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"读取社区索引缓存失败: {e}", exc_info=True)
            return jsonify({"message": f"读取社区索引缓存失败: {str(e)}"}), 500

    async def _api_install_community_pack(self):
        data = None
        try:
            data = await request.get_json()
            payload = data or {}
            overwrite = bool(payload.get("overwrite", False))
            set_as_default = bool(payload.get("set_as_default", False))
            pack_id = str(payload.get("pack_id") or "").strip()

            source = payload.get("source")
            if not isinstance(source, dict):
                if not pack_id:
                    return (
                        jsonify(
                            {
                                "message": "请提供 source 或 pack_id（用于从缓存索引安装）"
                            }
                        ),
                        400,
                    )
                source = find_cached_pack_entry(pack_id).get("source")
                if not isinstance(source, dict):
                    return jsonify({"message": "缓存条目缺少 source 信息"}), 400

            result = await self._run_guarded_runtime_file_operation(
                "安装社区资源包",
                install_pack_from_github_source,
                source=source,
                overwrite=overwrite,
                set_as_default=set_as_default,
                github_accelerator_url=self._get_github_accelerator_url(),
            )
            self._reload_personas()
            return jsonify({"message": "社区表情包安装成功", **result}), 200
        except FileExistsError as e:
            return jsonify({"message": str(e)}), 409
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except (FileNotFoundError, ValueError) as e:
            logger.warning(
                "社区表情包安装参数或资源错误: %s | pack_id=%s | payload_source=%s",
                e,
                str((data or {}).get("pack_id") or "").strip(),
                bool(isinstance((data or {}).get("source"), dict)),
            )
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"安装社区表情包失败: {e}", exc_info=True)
            return jsonify({"message": f"安装社区表情包失败: {str(e)}"}), 500

    async def _api_install_official_first_pack(self):
        data = None
        try:
            data = await request.get_json()
            payload = data or {}
            overwrite = bool(payload.get("overwrite", False))
            set_as_default = bool(payload.get("set_as_default", True))

            result = await self._run_guarded_runtime_file_operation(
                "安装官方资源包",
                install_first_official_pack_from_index,
                index_url=COMMUNITY_INDEX_URL,
                overwrite=overwrite,
                set_as_default=set_as_default,
                github_accelerator_url=self._get_github_accelerator_url(),
            )
            self._reload_personas()
            return jsonify({"message": "官方表情包安装成功", **result}), 200
        except FileExistsError as e:
            return jsonify({"message": str(e)}), 409
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except (FileNotFoundError, ValueError) as e:
            logger.warning(
                "安装官方首个表情包失败: %s | payload=%s",
                e,
                data,
            )
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"安装官方首个表情包失败: {e}", exc_info=True)
            return jsonify({"message": f"安装官方首个表情包失败: {str(e)}"}), 500

    async def _api_settings_rules(self):
        if request.method == "GET":
            try:
                return jsonify(get_selection_rules()), 200
            except Exception as e:
                logger.error(f"获取规则失败: {e}", exc_info=True)
                return jsonify({"message": f"获取规则失败: {str(e)}"}), 500

        try:
            data = await request.get_json()
            rules = (data or {}).get("rules", [])
            before = get_selection_rules()
            before_map = {
                str(item.get("id") or ""): str(item.get("pack_id") or "")
                for item in before.get("rules", [])
                if isinstance(item, dict)
            }
            saved = save_selection_rules(rules)
            self._reload_personas()
            return jsonify({"message": "规则保存成功", **saved}), 200
        except ValueError as e:
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"保存规则失败: {e}", exc_info=True)
            return jsonify({"message": f"保存规则失败: {str(e)}"}), 500

    async def _api_export_runtime_backup(self):
        try:
            data = await request.get_json()
            output_dir = (data or {}).get("output_dir")
            backup = getattr(self, "pack_backup_service", None)
            export_operation = backup.export if backup is not None else export_runtime_backup
            result = await self._run_guarded_runtime_file_operation(
                "导出全量备份",
                export_operation,
                output_dir=output_dir,
            )
            return jsonify(
                {"message": "全量备份导出成功", **_public_export_result(result)}
            ), 200
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except Exception as e:
            logger.error(f"导出全量备份失败: {e}", exc_info=True)
            return jsonify({"message": f"导出全量备份失败: {str(e)}"}), 500

    async def _api_settings_targets(self):
        try:
            rules_payload = get_selection_rules()
            rules = (
                rules_payload.get("rules", [])
                if isinstance(rules_payload, dict)
                else []
            )

            session_targets = []
            seen_session_targets = set()
            if isinstance(rules, list):
                for rule in rules:
                    if not isinstance(rule, dict):
                        continue
                    if str(rule.get("scope") or "").strip() != "session":
                        continue
                    target = str(rule.get("target") or "").strip()
                    if not target or target in seen_session_targets:
                        continue
                    seen_session_targets.add(target)
                    session_targets.append(target)

            persona_targets = []
            personas = getattr(self.context.provider_manager, "personas", [])
            for index, persona in enumerate(
                personas if isinstance(personas, list) else []
            ):
                if not isinstance(persona, dict):
                    continue
                if hasattr(self, "_get_persona_key"):
                    persona_id = str(self._get_persona_key(persona, index)).strip()
                else:
                    persona_id = str(
                        persona.get("id") or persona.get("name") or index
                    ).strip()
                if not persona_id:
                    continue
                persona_name = str(persona.get("name") or persona_id)
                persona_targets.append({"id": persona_id, "label": persona_name})

            return (
                jsonify(
                    {
                        "persona_targets": persona_targets,
                        "session_targets": session_targets,
                    }
                ),
                200,
            )
        except Exception as e:
            logger.error(f"获取规则 target 建议值失败: {e}", exc_info=True)
            return jsonify({"message": f"获取规则 target 建议值失败: {str(e)}"}), 500

    async def _api_import_runtime_backup(self):
        temp_zip_path = None
        try:
            self._prepare_archive_upload_request()
            overwrite_param = request.args.get("overwrite")
            form = await request.form
            json_payload = await request.get_json(silent=True)

            overwrite_raw = overwrite_param
            if overwrite_raw is None:
                if isinstance(form, dict) and form.get("overwrite") is not None:
                    overwrite_raw = form.get("overwrite")
                elif isinstance(json_payload, dict):
                    overwrite_raw = json_payload.get("overwrite", "false")
                else:
                    overwrite_raw = "false"

            overwrite = str(overwrite_raw).lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = f"runtime_restore_{int(time.time() * 1000)}.zip"
            temp_zip_path = (TEMP_DIR / safe_name).resolve()

            files = await request.files
            if files and "file" in files:
                archive_file = files["file"]
                if not archive_file or not archive_file.filename:
                    return jsonify({"message": "无效的备份文件"}), 400
                if not str(archive_file.filename).lower().endswith(".zip"):
                    return jsonify({"message": "仅支持 zip 备份文件"}), 400
                await self._save_uploaded_file(archive_file, temp_zip_path)
                if temp_zip_path.stat().st_size > MAX_PACK_ARCHIVE_BYTES:
                    raise ValueError("压缩包超过 1 GB，无法通过 WebUI 导入")
            elif isinstance(json_payload, dict):
                file_name = str(json_payload.get("file_name") or "").strip()
                file_b64 = str(json_payload.get("file_b64") or "").strip()
                if not file_name or not file_name.lower().endswith(".zip"):
                    return jsonify({"message": "仅支持 zip 备份文件"}), 400
                if not file_b64:
                    return jsonify({"message": "缺少 file_b64"}), 400
                try:
                    raw_bytes = _decode_bounded_base64(
                        file_b64, MAX_PACK_ARCHIVE_BYTES
                    )
                except ValueError as exc:
                    status = 413 if "超过" in str(exc) else 400
                    return jsonify({"message": str(exc)}), status
                temp_zip_path.write_bytes(raw_bytes)
                if temp_zip_path.stat().st_size > MAX_PACK_ARCHIVE_BYTES:
                    raise ValueError("备份文件超过 1 GB，无法通过 WebUI 导入")
            else:
                return (
                    jsonify({"message": "缺少上传文件字段 file 或 JSON file_b64"}),
                    400,
                )

            backup = getattr(self, "pack_backup_service", None)
            import_operation = backup.restore if backup is not None else import_runtime_backup
            result = await self._run_guarded_runtime_file_operation(
                "恢复全量备份",
                import_operation,
                temp_zip_path,
                overwrite=overwrite,
            )
            self._reload_personas()
            return jsonify({"message": "全量备份导入成功", **result}), 200
        except RuntimeError as e:
            return jsonify({"message": str(e)}), 409
        except RequestEntityTooLarge:
            return jsonify({"message": "备份文件超过 1 GB，无法通过 WebUI 导入"}), 413
        except (FileNotFoundError, ValueError) as e:
            return jsonify({"message": str(e)}), 400
        except Exception as e:
            logger.error(f"导入全量备份失败: {e}", exc_info=True)
            return jsonify({"message": f"导入全量备份失败: {str(e)}"}), 500
        finally:
            if temp_zip_path and temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                except Exception:
                    pass
