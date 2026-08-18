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
from ..config import BACKUP_DIR, TEMP_DIR

MAX_PACK_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_PACK_UPLOAD_REQUEST_BYTES = MAX_PACK_ARCHIVE_BYTES + 1024 * 1024
PACK_EXPORT_SESSION_TTL_SECONDS = 60 * 60




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
            sanitized = dict(result)
            sanitized.pop("pack_dir", None)
            return jsonify(sanitized)
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

    def _pack_export_session_paths(self, token: str) -> tuple[Path, Path]:
        normalized = str(token or "").strip().lower()
        if len(normalized) != 32 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("导出凭证无效，请重新导出")
        session_dir = TEMP_DIR / "pack_export_sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / f"{normalized}.zip", session_dir / f"{normalized}.json"

    def _cleanup_pack_export_sessions(self) -> None:
        """Remove expired export sessions so no archive lingers indefinitely."""
        session_dir = TEMP_DIR / "pack_export_sessions"
        if not session_dir.is_dir():
            return
        expire_before = time.time() - PACK_EXPORT_SESSION_TTL_SECONDS
        for path in session_dir.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < expire_before:
                    path.unlink()
            except OSError:
                continue

    def _load_pack_export_session(self, token: str) -> dict:
        _session_archive_path, metadata_path = self._pack_export_session_paths(token)
        if not metadata_path.is_file():
            raise ValueError("导出凭证已失效，请重新导出")
        try:
            session_data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("导出凭证损坏，请重新导出") from exc
        if not isinstance(session_data, dict):
            raise ValueError("导出凭证损坏，请重新导出")
        return session_data

    async def _api_pack_export_prepare(self):
        session_token = None
        metadata_path = None
        succeeded = False
        try:
            self._cleanup_pack_export_sessions()
            data = await request.get_json() or {}
            if not isinstance(data, dict):
                return jsonify({"message": "请求体无效"}), 400
            pack_id = str(data.get("pack_id") or "").strip()
            export_mode = str(data.get("mode") or "share").strip().lower()
            if not pack_id:
                return jsonify({"message": "pack_id 不能为空"}), 400
            transfer = getattr(self, "pack_transfer_service", None)
            export_operation = (
                transfer.export if transfer is not None else export_pack_archive
            )
            result = await self._run_guarded_pack_file_operation(
                pack_id,
                "导出资源包",
                export_operation,
                pack_id,
                export_mode=export_mode,
            )
            archive_path = Path(result["archive_path"])
            backup_root = BACKUP_DIR.resolve(strict=False)
            try:
                archive_path.resolve(strict=False).relative_to(backup_root)
            except ValueError as exc:
                raise ValueError("导出文件位置无效") from exc
            if (
                not archive_path.is_file()
                or archive_path.suffix.lower() != ".zip"
            ):
                raise ValueError("导出压缩包生成失败")
            session_token = secrets.token_hex(16)
            _session_zip_path, metadata_path = self._pack_export_session_paths(
                session_token
            )
            archive_filename = str(
                result.get("archive_filename") or archive_path.name
            )
            session_data = {
                "pack_id": pack_id,
                "mode": export_mode,
                "archive_path": str(archive_path.resolve(strict=False)),
                "archive_filename": archive_filename,
                "created_at": time.time(),
                "expires_at": time.time() + PACK_EXPORT_SESSION_TTL_SECONDS,
            }
            metadata_path.write_text(
                json.dumps(session_data, ensure_ascii=False),
                encoding="utf-8",
            )
            succeeded = True
            return jsonify(
                {
                    "message": "导出压缩包已生成，开始下载",
                    "download_token": session_token,
                    "archive_filename": archive_filename,
                    "pack_id": pack_id,
                    "mode": export_mode,
                }
            ), 200
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("生成导出压缩包失败: %s", exc, exc_info=True)
            return jsonify({"message": "生成导出压缩包失败"}), 500
        finally:
            if not succeeded and metadata_path is not None:
                try:
                    metadata_path.unlink(missing_ok=True)
                except OSError:
                    pass

    async def _api_pack_export_download(self):
        token = str(request.args.get("token") or "").strip()
        metadata_path = None
        try:
            self._cleanup_pack_export_sessions()
            if not token:
                return jsonify({"message": "缺少下载凭证"}), 400
            _session_zip_path, metadata_path = self._pack_export_session_paths(token)
            session_data = self._load_pack_export_session(token)
            expires_at = float(session_data.get("expires_at") or 0)
            if time.time() > expires_at:
                raise ValueError("导出凭证已过期，请重新导出")
            archive_path = Path(
                str(session_data.get("archive_path") or "")
            ).resolve(strict=False)
            backup_root = BACKUP_DIR.resolve(strict=False)
            try:
                archive_path.relative_to(backup_root)
            except ValueError as exc:
                raise ValueError("导出凭证无效") from exc
            if not archive_path.is_file() or archive_path.suffix.lower() != ".zip":
                raise ValueError("导出文件不存在，请重新导出")
            archive_filename = str(
                session_data.get("archive_filename") or archive_path.name
            )
            response = await send_file(
                archive_path,
                mimetype="application/zip",
                as_attachment=True,
                attachment_filename=archive_filename,
            )

            def _cleanup_session() -> None:
                for path in (metadata_path,):
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass

            call_on_close = getattr(response, "call_on_close", None)
            if callable(call_on_close):
                call_on_close(_cleanup_session)
            else:
                _cleanup_session()
            return response
        except FileNotFoundError as exc:
            return jsonify({"message": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("下载导出压缩包失败: %s", exc, exc_info=True)
            return jsonify({"message": "下载导出压缩包失败"}), 500

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
