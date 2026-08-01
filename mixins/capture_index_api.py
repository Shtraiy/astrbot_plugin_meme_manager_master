from __future__ import annotations

import asyncio
import re
from pathlib import Path

from quart import jsonify, request

from astrbot.api import logger

from ..capture_activity import load_capture_activity
from ..config import PACKS_DIR, get_active_pack_paths
from ..storage import MemeStore, is_safe_category_segment


class CaptureIndexAPIMixin:
    """Web endpoints for the capture activity and catalog workspace."""

    def _capture_pack_id(self, data: dict | None = None) -> str:
        payload = data if isinstance(data, dict) else {}
        pack_id = str(
            payload.get("pack_id")
            or request.args.get("pack_id")
            or request.args.get("managed_pack_id")
            or ""
        ).strip()
        if not pack_id:
            try:
                pack_id = str(get_active_pack_paths().get("pack_id") or "").strip()
            except Exception:
                pack_id = ""
        if not pack_id or not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", pack_id):
            raise ValueError("pack_id 无效")

        pack_dir = (PACKS_DIR / pack_id).resolve()
        try:
            pack_dir.relative_to(PACKS_DIR.resolve())
        except ValueError as exc:
            raise ValueError("pack_id 无效") from exc
        if not pack_dir.is_dir():
            raise FileNotFoundError(f"表情包 {pack_id} 不存在")
        return pack_id

    @staticmethod
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
        indexed_items.sort(key=self._capture_item_time, reverse=True)
        pending_items.sort(key=self._capture_item_time, reverse=True)

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

    async def _api_capture_workspace(self):
        try:
            pack_id = self._capture_pack_id()
            return jsonify(self._capture_workspace_for_pack(pack_id))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取偷取表情包工作台失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取偷取表情包工作台失败"}), 500

    async def _api_capture_index(self):
        try:
            data = await request.get_json() or {}
            pack_id = self._capture_pack_id(data)
            pack_dir = (PACKS_DIR / pack_id).resolve()
            active_store = getattr(self, "store", None)
            if active_store is None or Path(active_store.root).resolve() != pack_dir:
                return (
                    jsonify({"message": "请先将该资源包设为当前运行资源包后再处理偷取索引"}),
                    409,
                )
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
