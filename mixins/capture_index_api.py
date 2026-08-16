from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path

from quart import jsonify, request

from astrbot.api import logger

from ..capture_activity import (
    load_capture_activity,
    mark_capture_events_ignored,
)
from ..config import PACKS_DIR, get_active_pack_paths
from ..backend.tagging import canonical_tag
from ..backend.catalog_index_service import CatalogIndexService
from ..indexing import (
    LIBRARY_INDEX_PROMPT_VERSION,
    LIBRARY_INDEX_VERSION,
    full_reindex_entry_is_current,
)
from ..storage import IMAGE_EXTENSIONS, MemeStore


CAPTURE_WORKSPACE_PAGE_SIZE = 48
CAPTURE_DISPOSE_LIMIT = 500


class CaptureIndexAPIMixin:
    """Web endpoints for the capture activity and catalog workspace."""

    def _capture_catalog_index_service(self) -> CatalogIndexService:
        service = getattr(self, "catalog_index_service", None)
        if service is not None:
            return service
        return CatalogIndexService(PACKS_DIR)

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

    def _capture_workspace_for_pack(
        self,
        pack_id: str,
        category: str = "",
        *,
        page: int = 1,
        v4_status: str = "all",
    ) -> dict:
        return self._flat_capture_workspace_for_pack(
            pack_id, category, page=page, v4_status=v4_status
        )

    @staticmethod
    def _v4_status_for_entry(entry: dict) -> str:
        if not entry.get("indexed"):
            return "pending"
        digest = str(entry.get("sha256") or "")
        if full_reindex_entry_is_current(
            entry,
            digest,
            index_version=LIBRARY_INDEX_VERSION,
            prompt_version=LIBRARY_INDEX_PROMPT_VERSION,
        ):
            return "complete"
        return "needs_rebuild"

    def _flat_capture_workspace_for_pack(
        self,
        pack_id: str,
        category: str = "",
        *,
        page: int = 1,
        v4_status: str = "all",
    ) -> dict:
        """Build the capture workspace from flat files and virtual tags."""
        v4_status = str(v4_status or "all").strip().lower()
        if v4_status not in {"all", "complete", "needs_rebuild", "pending", "duplicate"}:
            raise ValueError("v4_status 无效")
        selected_tag = canonical_tag(category) if str(category or "").strip() else None
        if category and not selected_tag:
            raise ValueError("invalid tag")
        try:
            requested_page = max(1, int(page))
        except (TypeError, ValueError) as exc:
            raise ValueError("page 无效") from exc
        pack_dir = (PACKS_DIR / pack_id).resolve()
        store = MemeStore(pack_dir)
        store.reindex_flat_catalog()
        activity = load_capture_activity(pack_dir)
        indexed_by_filename: dict[str, dict] = {}
        pending_by_filename: dict[str, dict] = {}
        entry_v4_status: dict[str, str] = {}
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
            item_v4_status = self._v4_status_for_entry(entry)
            entry_v4_status[filename] = item_v4_status
            modified_at = int(path.stat().st_mtime)
            tags = sorted({
                normalized
                for raw_tag in entry.get("tags", [])
                if (normalized := canonical_tag(raw_tag))
            }) or ["其他"]
            for tag in tags:
                counts = tag_counts.setdefault(tag, {"total": 0, "indexed": 0, "pending": 0})
                counts["total"] += 1
                counts["indexed" if indexed else "pending"] += 1
                if selected_tag and tag != selected_tag:
                    continue
                item = {
                    **entry,
                    "tags": tags,
                    "category": tag,
                    "tag": tag,
                    "filename": filename,
                    "relative_path": f"memes/{filename}",
                    "indexed": indexed,
                    "v4_status": item_v4_status,
                    "captured_at": int(entry.get("captured_at") or modified_at),
                }
                if not indexed:
                    item["activity_status"] = "pending"
                target = indexed_by_filename if indexed else pending_by_filename
                existing = target.get(filename)
                if existing is None:
                    target[filename] = item
                else:
                    existing["tags"] = sorted(set(existing.get("tags", [])) | set(tags))
        for tag, counts in sorted(tag_counts.items()):
            folders.append({
                "category": tag,
                "tag": tag,
                **counts,
                "complete": counts["indexed"] == counts["total"],
                "indexed_at": None,
                "index_provider_id": "",
            })
        duplicate_digests: list[str] = []
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
            digest = str(event.get("sha256") or "").lower()
            if re.fullmatch(r"[0-9a-f]{64}", digest) and digest not in duplicate_digests:
                duplicate_digests.append(digest)
            duplicate_item = {
                "id": event.get("id", ""),
                "category": event_tag,
                "tag": event_tag,
                "tags": [event_tag] if event_tag else ["其他"],
                "filename": filename,
                "sha256": event.get("sha256", ""),
                "relative_path": f"memes/{filename}",
                "indexed": False,
                "duplicate": True,
                "v4_status": "duplicate",
                "activity_status": "duplicate",
                "duplicate_of": event.get("duplicate_of", ""),
                "captured_at": event.get("captured_at", 0),
            }
            existing = pending_by_filename.get(filename) or indexed_by_filename.pop(filename, None)
            if existing is None:
                pending_by_filename[filename] = duplicate_item
            else:
                existing.update(duplicate_item)
                existing["tags"] = sorted(set(existing.get("tags", [])) | set(duplicate_item["tags"]))
                pending_by_filename[filename] = existing
        indexed_items = sorted(indexed_by_filename.values(), key=self._capture_item_time, reverse=True)
        pending_items = sorted(pending_by_filename.values(), key=self._capture_item_time, reverse=True)
        duplicate_count = sum(1 for item in pending_items if item.get("duplicate"))
        duplicate_filenames = {
            str(item.get("filename") or "")
            for item in pending_items
            if item.get("duplicate")
        }
        v4_complete = sum(
            1
            for filename, status in entry_v4_status.items()
            if status == "complete" and filename not in duplicate_filenames
        )
        v4_needs_rebuild = sum(
            1
            for filename, status in entry_v4_status.items()
            if status == "needs_rebuild" and filename not in duplicate_filenames
        )
        v4_pending = sum(
            1
            for filename, status in entry_v4_status.items()
            if status == "pending" and filename not in duplicate_filenames
        )
        v4_checked_total = v4_complete + v4_needs_rebuild
        v4_completion_percent = (
            round(v4_complete / v4_checked_total * 100) if v4_checked_total else None
        )
        v4_summary_status = (
            "none"
            if not v4_checked_total
            else "complete"
            if not v4_needs_rebuild
            else "partial"
        )
        v4_summary = {
            "complete": v4_complete,
            "needs_rebuild": v4_needs_rebuild,
            "pending": v4_pending,
            "duplicate": duplicate_count,
            "checked_total": v4_checked_total,
            "completion_percent": v4_completion_percent,
            "status": v4_summary_status,
        }
        if v4_status != "all":
            indexed_items = [
                item for item in indexed_items if item.get("v4_status") == v4_status
            ]
            pending_items = [
                item for item in pending_items if item.get("v4_status") == v4_status
            ]
        state = dict(getattr(self, "_library_index_state", {}) or {})
        active_store = getattr(self, "store", None)
        state["active_pack"] = bool(
            active_store is not None and Path(getattr(active_store, "root", "")).resolve() == pack_dir
        )
        visible_folders = [folder for folder in folders if not selected_tag or folder["tag"] == selected_tag]
        indexed_total_pages = max(1, (len(indexed_items) + CAPTURE_WORKSPACE_PAGE_SIZE - 1) // CAPTURE_WORKSPACE_PAGE_SIZE)
        pending_total_pages = 1
        current_page = min(requested_page, indexed_total_pages)
        page_start = (current_page - 1) * CAPTURE_WORKSPACE_PAGE_SIZE
        page_end = page_start + CAPTURE_WORKSPACE_PAGE_SIZE
        return {
            "pack_id": pack_id,
            "library_index": state,
            "summary": {
                "indexed": len(indexed_items),
                "pending": len(pending_items) - duplicate_count,
                "duplicate": duplicate_count,
                "complete_folders": sum(1 for folder in visible_folders if folder["complete"]),
                "folder_total": len(visible_folders),
                "v4": v4_summary,
            },
            "folders": folders,
            "duplicate_digests": duplicate_digests,
            "pagination": {
                "page": current_page,
                "page_size": CAPTURE_WORKSPACE_PAGE_SIZE,
                "indexed": {
                    "total": len(indexed_items),
                    "total_pages": indexed_total_pages,
                },
                "pending": {
                    "total": len(pending_items),
                    "total_pages": pending_total_pages,
                },
            },
            "indexed_items": indexed_items[page_start:page_end],
            "pending_items": pending_items,
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
            "classified": 0,
            "skipped": 0,
            "reindexed": 0,
            "errors": 0,
            "message": "正在准备重索引……",
        }

    @staticmethod
    def _reindex_state_is_resumable(state: dict | None) -> bool:
        return isinstance(state, dict) and str(state.get("status") or "") in {
            "queued",
            "running",
            "paused",
            "interrupted",
        }

    def _persist_reindex_state(self, pack_id: str, state: dict) -> None:
        pack_dir = (PACKS_DIR / str(pack_id)).resolve()
        if not pack_dir.is_dir():
            return
        try:
            MemeStore(pack_dir).write_reindex_state(state)
        except Exception as exc:
            logger.warning("持久化全量语义重索引状态失败 pack=%s: %s", pack_id, exc)

    def _load_persisted_reindex_state(self, pack_id: str) -> dict:
        pack_dir = (PACKS_DIR / str(pack_id)).resolve()
        if not pack_dir.is_dir():
            return {}
        try:
            state = MemeStore(pack_dir).load_reindex_state()
        except Exception as exc:
            logger.warning("读取全量语义重索引状态失败 pack=%s: %s", pack_id, exc)
            return {}
        return state if state.get("pack_id") in (None, str(pack_id)) else {}

    def _start_reindex_task(
        self,
        pack_id: str,
        state: dict[str, int | str],
        *,
        resume: bool = False,
    ) -> asyncio.Task:
        tasks = getattr(self, "_reindex_tasks", {})
        existing = tasks.get(pack_id)
        if existing is not None and not existing.done():
            return existing
        if resume:
            state.update(
                status="running",
                message=state.get("message") or "正在恢复全量语义重索引……",
            )
        self._persist_reindex_state(pack_id, state)
        task = asyncio.create_task(self._run_reindex_task(pack_id, state))
        tasks[pack_id] = task
        self._reindex_tasks = tasks
        return task

    async def _reindex_pack_catalog_with_progress(
        self, pack_id: str, state: dict[str, int | str]
    ) -> dict[str, int | str]:
        pack_dir = (PACKS_DIR / str(pack_id)).resolve()
        store = MemeStore(pack_dir)
        result = await self._ensure_flat_library_index(
            target_store=store,
            progress_state=state,
            full_reindex=True,
        )
        catalog = store.load_catalog()
        category_count = len(
            {
                tag
                for item in catalog.get("items", [])
                if isinstance(item, dict)
                for tag in item.get("tags", [])
            }
        )
        state["current_category"] = ""
        return {
            "pack_id": str(pack_id),
            "category_count": category_count,
            "changed_file_count": result.get("changed_file_count", 0),
            "processed": result.get("processed", 0),
            "total": result.get("total", 0),
            "skipped": result.get("skipped", 0),
            "reindexed": result.get("reindexed", 0),
            "errors": result.get("errors", 0),
            **result,
        }
    async def _run_reindex_task(
        self, pack_id: str, state: dict[str, int | str]
    ) -> None:
        try:
            # Model calls and progress persistence must not hold the pack
            # mutation lock.  The indexer takes short write locks only when
            # committing a checkpoint/final merge, so delete/ignore can run
            # while a long vision request is in flight.
            result = await self._reindex_pack_catalog_with_progress(pack_id, state)
            state.update(result)
            if state.get("status") == "blocked":
                self._persist_reindex_state(pack_id, state)
                return
            errors = int(state.get("errors") or 0)
            state.update(
                status="completed" if not errors else "completed_with_errors",
                current_category="",
                message=(
                    f"全量语义重索引完成：跳过 {state.get('skipped', 0)} 张，"
                    f"重新识别 {state.get('reindexed', 0)} 张，"
                    f"失败 {errors} 张；整理 {result.get('changed_file_count', 0)} 个文件名"
                ),
            )
            self._persist_reindex_state(pack_id, state)
        except asyncio.CancelledError:
            state.update(
                status="paused",
                message="全量语义重索引已暂停，重新打开页面后会从检查点继续",
            )
            self._persist_reindex_state(pack_id, state)
            raise
        except Exception as exc:
            logger.error("重索引表情包失败: %s", exc, exc_info=True)
            state.update(status="error", message=f"重索引失败：{exc}")
            self._persist_reindex_state(pack_id, state)

    async def _api_capture_workspace(self):
        try:
            pack_id = self._capture_pack_id()
            category = str(request.args.get("category") or "").strip()
            page = request.args.get("page", "1")
            v4_status = str(request.args.get("v4_status") or "all").strip()
            return jsonify(
                self._capture_workspace_for_pack(
                    pack_id, category, page=page, v4_status=v4_status
                )
            )
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取偷取表情包工作台失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取偷取表情包工作台失败"}), 500

    async def _api_capture_index(self):
        try:
            data = await request.get_json() or {}
            if not isinstance(data, dict):
                return jsonify({"message": "请求体无效"}), 400
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
            if any(
                task is not None and not task.done()
                for task in getattr(self, "_reindex_tasks", {}).values()
            ):
                return jsonify({"message": "全量语义重索引正在处理中", "status": "running"}), 409
            selected_filenames = None
            if "items" in data:
                selected_filenames = self._prepare_selected_capture_index_items(
                    pack_dir, data.get("items")
                )
                if not selected_filenames:
                    return jsonify({"message": "没有可索引的待处理表情"}), 400
            self._library_completed_key = None
            self._library_retry_key = None
            self._library_retry_at = 0.0
            self._library_index_state.update(
                status="queued",
                processed=0,
                total=0,
                classified=0,
                errors=0,
                selected_count=len(selected_filenames) if selected_filenames is not None else 0,
                message="已提交分类索引，正在启动……",
            )
            task = asyncio.create_task(
                self._ensure_library_index(selected_filenames=selected_filenames)
            )
            self._library_task = task
            task.add_done_callback(self._log_library_task_failure)
            return jsonify({"message": "已开始处理待分类偷取表情包", "status": "running"}), 202
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("启动偷取表情包索引失败: %s", exc, exc_info=True)
            return jsonify({"message": "启动偷取表情包索引失败"}), 500

    def _prepare_selected_capture_index_items(
        self, pack_dir: Path, raw_items: object
    ) -> set[str]:
        """Validate a selection and return only current ordinary pending files."""
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("索引项目不能为空")
        if len(raw_items) > CAPTURE_DISPOSE_LIMIT:
            raise ValueError("索引项目过多")
        store = MemeStore(pack_dir)
        catalog_by_filename = {
            str(entry.get("filename")): entry
            for entry in store.load_catalog().get("items", [])
            if isinstance(entry, dict) and entry.get("filename")
        }
        duplicate_digests = {
            str(event.get("sha256") or "").lower()
            for event in load_capture_activity(pack_dir).get("events", [])
            if isinstance(event, dict) and event.get("status") == "duplicate"
        }
        selected: set[str] = set()
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise ValueError("索引项目无效")
            if str(raw_item.get("kind") or "").strip().lower() != "pending":
                # Duplicate cards remain on the ignore path and are never
                # sent to the classifier, even if a stale client includes one.
                continue
            filename = self._capture_dispose_filename(raw_item.get("filename"))
            entry = catalog_by_filename.get(filename)
            path = store.memes_dir / filename
            if entry is None or bool(entry.get("indexed")) or not path.is_file():
                continue
            expected_digest = str(raw_item.get("sha256") or "").strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
                continue
            actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_digest != expected_digest or actual_digest in duplicate_digests:
                continue
            selected.add(filename)
        return selected

    async def _api_capture_ignore_duplicates(self):
        try:
            data = await request.get_json() or {}
            if not isinstance(data, dict):
                return jsonify({"message": "请求体无效"}), 400
            pack_id = self._capture_pack_id(data)
            raw_digests = data.get("sha256s")
            if not isinstance(raw_digests, list) or not raw_digests:
                return jsonify({"message": "图片指纹列表不能为空"}), 400
            if len(raw_digests) > CAPTURE_DISPOSE_LIMIT:
                return jsonify({"message": "图片指纹列表过大"}), 400
            digests: set[str] = set()
            for value in raw_digests:
                if not isinstance(value, str):
                    return jsonify({"message": "图片指纹无效"}), 400
                digest = value.strip().lower()
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    return jsonify({"message": "图片指纹无效"}), 400
                digests.add(digest)
            pack_dir = (PACKS_DIR / pack_id).resolve()
            active_store = getattr(self, "store", None)
            if active_store is None or Path(active_store.root).resolve() != pack_dir:
                return (
                    jsonify({"message": "请先将该资源包设为当前运行资源包后再忽略重复记录"}),
                    409,
                )
            def mutate():
                blacklisted_count = self.capture_blacklist.add(digests)
                ignored = mark_capture_events_ignored(pack_dir, digests=digests)
                return {
                    "message": "已忽略重复记录并加入黑名单",
                    "ignored": ignored,
                    "blacklisted_count": blacklisted_count,
                }

            result = await self._capture_catalog_index_service().run_locked_pack_mutation(
                pack_id, "忽略重复捕获记录", mutate
            )
            return jsonify(result)
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("忽略重复捕获记录失败: %s", exc, exc_info=True)
            return jsonify({"message": "忽略重复捕获记录失败"}), 500

    @staticmethod
    def _capture_dispose_filename(value: object) -> str:
        filename = str(value or "").strip()
        if (
            not filename
            or Path(filename).name != filename
            or Path(filename).suffix.lower() not in IMAGE_EXTENSIONS
        ):
            raise ValueError("图片文件名无效")
        return filename

    def _prepare_capture_disposals(
        self, pack_dir: Path, items: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        store = MemeStore(pack_dir)
        catalog_by_filename = {
            str(entry.get("filename")): entry
            for entry in store.load_catalog().get("items", [])
            if isinstance(entry, dict) and entry.get("filename")
        }
        duplicate_digests = {
            str(event.get("sha256") or "").lower()
            for event in load_capture_activity(pack_dir).get("events", [])
            if isinstance(event, dict) and event.get("status") == "duplicate"
        }
        prepared: list[dict] = []
        failed: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            kind = str(item.get("kind") or "").strip().lower()
            if kind == "duplicate":
                digest = str(item.get("sha256") or "").strip().lower()
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError("图片指纹无效")
                identity = (kind, digest)
                if identity in seen:
                    continue
                seen.add(identity)
                if digest not in duplicate_digests:
                    failed.append({
                        "kind": kind,
                        "sha256": digest,
                        "reason": "重复记录不存在或已处理",
                    })
                    continue
                prepared.append({"kind": kind, "sha256": digest})
                continue

            if kind not in {"indexed", "pending"}:
                raise ValueError("处置类型无效")
            filename = self._capture_dispose_filename(item.get("filename"))
            identity = (kind, filename)
            if identity in seen:
                continue
            seen.add(identity)
            entry = catalog_by_filename.get(filename)
            path = store.memes_dir / filename
            expected_indexed = kind == "indexed"
            if entry is None or not path.is_file() or bool(entry.get("indexed")) != expected_indexed:
                failed.append({"kind": kind, "filename": filename, "reason": "图片不存在或状态已变化"})
                continue
            prepared.append({
                "kind": kind,
                "filename": filename,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        return prepared, failed

    @staticmethod
    def _dispose_capture_items(
        pack_dir: Path, prepared: list[dict], failed: list[dict]
    ) -> list[dict]:
        store = MemeStore(pack_dir)
        succeeded: list[dict] = []
        deleted_names: set[str] = set()
        for item in prepared:
            kind = item["kind"]
            if kind == "duplicate":
                ignored = mark_capture_events_ignored(pack_dir, digests={item["sha256"]})
                if ignored:
                    succeeded.append(dict(item))
                else:
                    failed.append({
                        **item,
                        "blacklisted": True,
                        "reason": "重复记录不存在或已处理",
                    })
                continue
            path = store.memes_dir / item["filename"]
            try:
                path.unlink()
            except OSError as exc:
                failed.append({
                    **item,
                    "blacklisted": True,
                    "reason": f"删除失败：{exc}",
                })
                continue
            deleted_names.add(item["filename"])
            if kind == "pending":
                mark_capture_events_ignored(
                    pack_dir,
                    digests={item["sha256"]},
                    statuses={"pending", "duplicate"},
                )
            succeeded.append(dict(item))
        if deleted_names:
            catalog = store.load_catalog()
            metadata = {
                key: value
                for key, value in catalog.items()
                if key not in {"version", "updated_at", "items", "category"}
            }
            store.write_catalog(
                [
                    entry
                    for entry in catalog.get("items", [])
                    if isinstance(entry, dict) and entry.get("filename") not in deleted_names
                ],
                metadata,
            )
        return succeeded

    async def _api_capture_dispose_items(self):
        try:
            data = await request.get_json() or {}
            if not isinstance(data, dict):
                return jsonify({"message": "请求体无效"}), 400
            pack_id = self._capture_pack_id(data)
            items = data.get("items")
            if not isinstance(items, list) or not items:
                return jsonify({"message": "处置项目不能为空"}), 400
            if len(items) > CAPTURE_DISPOSE_LIMIT:
                return jsonify({"message": "处置项目过多"}), 400
            if not all(isinstance(item, dict) for item in items):
                return jsonify({"message": "处置项目无效"}), 400
            pack_dir = (PACKS_DIR / pack_id).resolve()

            def mutate():
                prepared, failed = self._prepare_capture_disposals(pack_dir, items)
                try:
                    blacklisted_count = self.capture_blacklist.add(
                        {item["sha256"] for item in prepared}
                    )
                except Exception as exc:
                    raise RuntimeError("写入捕获黑名单失败") from exc
                succeeded = self._dispose_capture_items(pack_dir, prepared, failed)
                return {
                    "message": "统一处理完成",
                    "succeeded": succeeded,
                    "failed": failed,
                    "disposed_count": len(succeeded),
                    "failed_count": len(failed),
                    "blacklisted_count": blacklisted_count,
                }

            return jsonify(await self._capture_catalog_index_service().run_locked_pack_mutation(
                pack_id, "统一处置捕获表情", mutate
            ))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except RuntimeError as exc:
            status = 500 if "黑名单" in str(exc) else 409
            return jsonify({"message": str(exc)}), status
        except Exception as exc:
            logger.error("统一处置捕获表情失败: %s", exc, exc_info=True)
            return jsonify({"message": "统一处置捕获表情失败"}), 500

    async def _api_capture_ignore_all_items(self):
        """Ignore every pending/duplicate capture in the selected pack."""
        try:
            data = await request.get_json() or {}
            if not isinstance(data, dict):
                return jsonify({"message": "请求体无效"}), 400
            pack_id = self._capture_pack_id(data)
            pack_dir = (PACKS_DIR / pack_id).resolve()

            def mutate():
                store = MemeStore(pack_dir)
                catalog = store.load_catalog()
                events = load_capture_activity(pack_dir).get("events", [])
                duplicate_filenames = {
                    Path(str(event.get("filename") or "")).name
                    for event in events
                    if isinstance(event, dict) and event.get("status") == "duplicate"
                }
                digests: set[str] = set()
                pending_names: set[str] = set()
                for entry in catalog.get("items", []):
                    if not isinstance(entry, dict) or bool(entry.get("indexed")):
                        continue
                    filename = str(entry.get("filename") or "")
                    path = store.memes_dir / filename
                    if not filename or not path.is_file() or filename in duplicate_filenames:
                        continue
                    pending_names.add(filename)
                    digests.add(hashlib.sha256(path.read_bytes()).hexdigest())
                for event in events:
                    if not isinstance(event, dict) or event.get("status") != "duplicate":
                        continue
                    digest = str(event.get("sha256") or "").strip().lower()
                    if re.fullmatch(r"[0-9a-f]{64}", digest):
                        digests.add(digest)
                if not digests:
                    return {
                        "message": "当前资源包没有待处理或待忽略表情",
                        "ignored_count": 0,
                        "disposed_count": 0,
                        "blacklisted_count": 0,
                    }
                try:
                    blacklisted_count = self.capture_blacklist.add(digests)
                except Exception as exc:
                    raise RuntimeError("写入捕获黑名单失败") from exc
                deleted_names: set[str] = set()
                for filename in pending_names:
                    try:
                        (store.memes_dir / filename).unlink()
                    except OSError as exc:
                        logger.warning("一键忽略待处理图片删除失败 filename=%s: %s", filename, exc)
                        continue
                    deleted_names.add(filename)
                if deleted_names:
                    metadata = {
                        key: value
                        for key, value in catalog.items()
                        if key not in {"version", "updated_at", "items", "category"}
                    }
                    store.write_catalog(
                        [
                            entry
                            for entry in catalog.get("items", [])
                            if not (
                                isinstance(entry, dict)
                                and entry.get("filename") in deleted_names
                            )
                        ],
                        metadata,
                    )
                mark_capture_events_ignored(
                    pack_dir,
                    digests=digests,
                    statuses={"pending", "duplicate"},
                )
                return {
                    "message": "已忽略当前资源包全部待处理和待忽略表情",
                    "ignored_count": len(digests),
                    "disposed_count": len(deleted_names),
                    "blacklisted_count": blacklisted_count,
                }

            result = await self._capture_catalog_index_service().run_locked_pack_mutation(
                pack_id, "一键忽略全部捕获表情", mutate
            )
            return jsonify(result)
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"message": str(exc)}), 500
        except Exception as exc:
            logger.error("一键忽略全部捕获表情失败: %s", exc, exc_info=True)
            return jsonify({"message": "一键忽略全部捕获表情失败"}), 500

    async def _api_capture_index_status(self):
        try:
            pack_id = self._capture_pack_id()
            state = dict(getattr(self, "_library_index_state", {}) or {})
            state.setdefault("status", "idle")
            state.setdefault("processed", 0)
            state.setdefault("total", 0)
            state.setdefault("classified", 0)
            state.setdefault("errors", 0)
            state.setdefault("message", "尚未开始目录索引")
            state["pack_id"] = pack_id
            return jsonify(state)
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取偷取表情包索引状态失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取偷取表情包索引状态失败"}), 500

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
            if any(
                running_pack != pack_id
                and task is not None
                and not task.done()
                for running_pack, task in getattr(self, "_reindex_tasks", {}).items()
            ):
                return jsonify({"message": "已有其他资源包正在全量语义重索引", "status": "running"}), 409
            states = getattr(self, "_reindex_states", {})
            state = states.get(pack_id)
            if state is None:
                state = self._load_persisted_reindex_state(pack_id)
            if self._reindex_state_is_resumable(state):
                states[pack_id] = state
                self._reindex_states = states
                self._start_reindex_task(pack_id, state, resume=True)
                return jsonify(dict(state))

            state = self._new_reindex_state(pack_id)
            states[pack_id] = state
            self._reindex_states = states
            self._start_reindex_task(pack_id, state)
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
            states = getattr(self, "_reindex_states", {})
            state = states.get(pack_id)
            if state is None:
                state = self._load_persisted_reindex_state(pack_id)
                if state:
                    states[pack_id] = state
                    self._reindex_states = states
                else:
                    state = None
            if self._reindex_state_is_resumable(state):
                self._start_reindex_task(pack_id, state, resume=True)
            if state is None:
                return jsonify({
                    "pack_id": pack_id,
                    "status": "idle",
                    "processed": 0,
                    "total": 0,
                    "changed_file_count": 0,
                    "classified": 0,
                    "skipped": 0,
                    "reindexed": 0,
                    "errors": 0,
                    "current_category": "",
                    "message": "尚未开始重索引",
                })
            return jsonify(dict(state))
        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        except Exception as exc:
            logger.error("读取重索引进度失败: %s", exc, exc_info=True)
            return jsonify({"message": "读取重索引进度失败"}), 500
