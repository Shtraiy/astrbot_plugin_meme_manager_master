from __future__ import annotations

import asyncio
import re
from pathlib import Path

from quart import jsonify, request

from astrbot.api import logger

from ..capture_activity import load_capture_activity
from ..config import PACKS_DIR, get_active_pack_paths
from ..backend.tagging import canonical_tag
from ..storage import MemeStore


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

    def _capture_workspace_for_pack(self, pack_id: str, category: str = "") -> dict:
        return self._flat_capture_workspace_for_pack(pack_id, category)

    def _flat_capture_workspace_for_pack(self, pack_id: str, category: str = "") -> dict:
        """Build the capture workspace from flat files and virtual tags."""
        selected_tag = canonical_tag(category) if str(category or "").strip() else None
        if category and not selected_tag:
            raise ValueError("invalid tag")
        pack_dir = (PACKS_DIR / pack_id).resolve()
        store = MemeStore(pack_dir)
        store.reindex_flat_catalog()
        activity = load_capture_activity(pack_dir)
        indexed_items: list[dict] = []
        pending_items: list[dict] = []
        folders: list[dict] = []
        tag_counts: dict[str, dict[str, int]] = {}
        for entry in store.load_catalog().get("items", []):
            if not isinstance(entry, dict):
                continue
            filename = Path(str(entry.get("filename") or "")).name
            path = store.memes_dir / filename
            if filename != str(entry.get("filename")) or not path.is_file():
                continue
            indexed = bool(entry.get("indexed"))
            modified_at = int(path.stat().st_mtime)
            for tag in entry.get("tags", []):
                counts = tag_counts.setdefault(tag, {"total": 0, "indexed": 0, "pending": 0})
                counts["total"] += 1
                counts["indexed" if indexed else "pending"] += 1
                if selected_tag and tag != selected_tag:
                    continue
                item = {
                    **entry,
                    "category": tag,
                    "tag": tag,
                    "filename": filename,
                    "relative_path": f"memes/{filename}",
                    "indexed": indexed,
                    "captured_at": int(entry.get("captured_at") or modified_at),
                }
                if indexed:
                    indexed_items.append(item)
                else:
                    item["activity_status"] = "pending"
                    pending_items.append(item)
        for tag, counts in sorted(tag_counts.items()):
            folders.append({
                "category": tag,
                "tag": tag,
                **counts,
                "complete": counts["indexed"] == counts["total"],
                "indexed_at": None,
                "index_provider_id": "",
            })
        duplicate_items = []
        duplicate_count = 0
        for event in activity.get("events", []):
            if not isinstance(event, dict) or event.get("status") != "duplicate":
                continue
            event_tag = canonical_tag(event.get("category")) or ""
            if selected_tag and event_tag != selected_tag:
                continue
            filename = str(event.get("filename") or "")
            path = store.memes_dir / Path(filename).name
            if not path.is_file():
                continue
            duplicate_count += 1
            duplicate_items.append({
                "id": event.get("id", ""),
                "category": event_tag,
                "tag": event_tag,
                "filename": filename,
                "sha256": event.get("sha256", ""),
                "relative_path": f"memes/{filename}",
                "indexed": False,
                "duplicate": True,
                "activity_status": "duplicate",
                "duplicate_of": event.get("duplicate_of", ""),
                "captured_at": event.get("captured_at", 0),
            })
        pending_items.extend(duplicate_items)
        indexed_items.sort(key=self._capture_item_time, reverse=True)
        pending_items.sort(key=self._capture_item_time, reverse=True)
        state = dict(getattr(self, "_library_index_state", {}) or {})
        active_store = getattr(self, "store", None)
        state["active_pack"] = bool(
            active_store is not None and Path(getattr(active_store, "root", "")).resolve() == pack_dir
        )
        visible_folders = [folder for folder in folders if not selected_tag or folder["tag"] == selected_tag]
        return {
            "pack_id": pack_id,
            "library_index": state,
            "summary": {
                "indexed": len(indexed_items),
                "pending": len(pending_items) - duplicate_count,
                "duplicate": duplicate_count,
                "complete_folders": sum(1 for folder in visible_folders if folder["complete"]),
                "folder_total": len(visible_folders),
            },
            "folders": folders,
            "indexed_items": indexed_items if selected_tag else indexed_items[:48],
            "pending_items": pending_items if selected_tag else pending_items[:48],
        }
    def _reindex_pack_catalog(self, pack_id: str) -> dict[str, int | str]:
        """Renumber local files and update catalog references without models."""
        pack_dir = (PACKS_DIR / str(pack_id)).resolve()
        if not pack_dir.is_dir():
            raise FileNotFoundError(f"表情包 {pack_id} 不存在")
        store = MemeStore(pack_dir)
        result = store.reindex_flat_catalog()
        return {
            "pack_id": str(pack_id),
            "category_count": result["tag_count"],
            "changed_file_count": result["migrated_file_count"],
            **result,
        }

    def _new_reindex_state(self, pack_id: str) -> dict[str, int | str]:
        pack_dir = (PACKS_DIR / str(pack_id)).resolve()
        if not pack_dir.is_dir():
            raise FileNotFoundError(f"表情包 {pack_id} 不存在")
        store = MemeStore(pack_dir)
        total = sum(
            1
            for path in store.memes_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {
                ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"
            }
        )
        return {
            "pack_id": str(pack_id),
            "status": "running",
            "processed": 0,
            "total": total,
            "changed_file_count": 0,
            "current_category": "",
            "message": "正在准备重索引……",
        }

    async def _reindex_pack_catalog_with_progress(
        self, pack_id: str, state: dict[str, int | str]
    ) -> dict[str, int | str]:
        pack_dir = (PACKS_DIR / str(pack_id)).resolve()
        store = MemeStore(pack_dir)
        result = await asyncio.to_thread(store.reindex_flat_catalog)
        state["processed"] = result["processed"]
        state["total"] = result["total"]
        state["changed_file_count"] = result["migrated_file_count"]
        state["current_category"] = ""
        return {
            "pack_id": str(pack_id),
            "category_count": result["tag_count"],
            "changed_file_count": result["migrated_file_count"],
            "processed": result["processed"],
            "total": result["total"],
            **result,
        }
    async def _run_reindex_task(
        self, pack_id: str, state: dict[str, int | str]
    ) -> None:
        try:
            result = await self.catalog_index_service.run_locked_pack_mutation(
                pack_id,
                "重索引表情文件",
                lambda: self._reindex_pack_catalog_with_progress(pack_id, state),
            )
            state.update(result)
            state.update(
                status="completed",
                current_category="",
                message=(
                    f"重索引完成：整理 {result['category_count']} 个分类，"
                    f"更新 {result['changed_file_count']} 个文件名"
                ),
            )
        except Exception as exc:
            logger.error("重索引表情包失败: %s", exc, exc_info=True)
            state.update(status="error", message=f"重索引失败：{exc}")

    async def _api_capture_workspace(self):
        try:
            pack_id = self._capture_pack_id()
            category = str(request.args.get("category") or "").strip()
            return jsonify(self._capture_workspace_for_pack(pack_id, category))
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
            self._library_index_state.update(
                status="queued",
                processed=0,
                total=0,
                classified=0,
                errors=0,
                message="已提交分类索引，正在启动……",
            )
            task = asyncio.create_task(self._ensure_library_index())
            self._library_task = task
            task.add_done_callback(self._log_library_task_failure)
            return jsonify({"message": "已开始处理待分类偷取表情包", "status": "running"}), 202
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("启动偷取表情包索引失败: %s", exc, exc_info=True)
            return jsonify({"message": "启动偷取表情包索引失败"}), 500

    async def _api_capture_reindex(self):
        try:
            data = await request.get_json() or {}
            pack_id = self._capture_pack_id(data)
            task = getattr(self, "_library_task", None)
            if task is not None and not task.done():
                return jsonify({"message": "分类索引正在处理中，请稍后再重索引", "status": "running"}), 409
            existing_task = getattr(self, "_reindex_tasks", {}).get(pack_id)
            if existing_task is not None and not existing_task.done():
                state = getattr(self, "_reindex_states", {}).get(pack_id, {})
                return jsonify(dict(state)), 409
            state = self._new_reindex_state(pack_id)
            states = getattr(self, "_reindex_states", {})
            tasks = getattr(self, "_reindex_tasks", {})
            states[pack_id] = state
            self._reindex_states = states
            task = asyncio.create_task(self._run_reindex_task(pack_id, state))
            tasks[pack_id] = task
            self._reindex_tasks = tasks
            return jsonify(dict(state))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 409
        except Exception as exc:
            logger.error("重索引表情包失败: %s", exc, exc_info=True)
            return jsonify({"message": "重索引表情包失败"}), 500

    async def _api_capture_reindex_status(self):
        try:
            pack_id = self._capture_pack_id()
            state = getattr(self, "_reindex_states", {}).get(pack_id)
            if state is None:
                return jsonify({
                    "pack_id": pack_id,
                    "status": "idle",
                    "processed": 0,
                    "total": 0,
                    "changed_file_count": 0,
                    "current_category": "",
                    "message": "尚未开始重索引",
                })
            return jsonify(dict(state))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取重索引进度失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取重索引进度失败"}), 500
