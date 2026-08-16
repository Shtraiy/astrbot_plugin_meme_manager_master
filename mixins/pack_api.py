from __future__ import annotations

import asyncio
import json
import secrets
import time
import zipfile
from pathlib import Path

from quart import jsonify, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from astrbot.api import logger

from ..backend.pack_storage import (
    export_pack_archive,
    get_pack_detail,
    get_pack_export_capabilities,
    import_pack_archive,
    inspect_pack_archive,
    list_installed_packs,
)

MAX_PACK_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_PACK_UPLOAD_REQUEST_BYTES = MAX_PACK_ARCHIVE_BYTES + 1024 * 1024




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
