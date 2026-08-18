"""Plugin-wide exact-content blacklist for automatically captured images."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

try:
    from .backend.atomic_io import atomic_write_json
except ImportError:  # standalone test imports (repo root on sys.path)
    from backend.atomic_io import atomic_write_json


CAPTURE_BLACKLIST_FILENAME = "capture_blacklist.json"
CAPTURE_BLACKLIST_SCHEMA_VERSION = 1
CAPTURE_AUTO_BLACKLIST_FILENAME = "capture_auto_blacklist.json"
CAPTURE_AUTO_BLACKLIST_SCHEMA_VERSION = 1
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}
T = TypeVar("T")


def _normalize_digest(value: object) -> str:
    digest = str(value or "").strip().lower()
    if not _DIGEST_PATTERN.fullmatch(digest):
        raise ValueError("图片 SHA-256 指纹无效")
    return digest


class CaptureBlacklist:
    """Persist and atomically consult the global capture blacklist."""

    def __init__(self, plugin_data_dir: Path | str):
        plugin_data_path = Path(plugin_data_dir).resolve()
        self.path = plugin_data_path / CAPTURE_BLACKLIST_FILENAME
        self.auto_path = plugin_data_path / CAPTURE_AUTO_BLACKLIST_FILENAME

    def _lock(self) -> threading.RLock:
        key = str(self.path)
        with _LOCKS_GUARD:
            return _PATH_LOCKS.setdefault(key, threading.RLock())

    def _load_unlocked(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            data: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("捕获黑名单文件损坏") from exc
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != CAPTURE_BLACKLIST_SCHEMA_VERSION
            or not isinstance(data.get("sha256s"), list)
        ):
            raise ValueError("捕获黑名单文件损坏")
        try:
            return {_normalize_digest(value) for value in data["sha256s"]}
        except ValueError as exc:
            raise ValueError("捕获黑名单文件损坏") from exc

    def _load_auto_unlocked(self) -> dict[str, list[dict[str, str]]]:
        if not self.auto_path.exists():
            return {}
        try:
            data: Any = json.loads(self.auto_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("自动捕获黑名单文件损坏") from exc
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != CAPTURE_AUTO_BLACKLIST_SCHEMA_VERSION
            or not isinstance(data.get("entries"), dict)
        ):
            raise ValueError("自动捕获黑名单文件损坏")
        normalized: dict[str, list[dict[str, str]]] = {}
        try:
            for raw_digest, raw_sources in data["entries"].items():
                digest = _normalize_digest(raw_digest)
                if not isinstance(raw_sources, list):
                    raise ValueError
                sources: list[dict[str, str]] = []
                for raw_source in raw_sources:
                    if not isinstance(raw_source, dict):
                        raise ValueError
                    pack_id = str(raw_source.get("pack_id") or "").strip()
                    filename = str(raw_source.get("filename") or "").strip()
                    if not pack_id or not filename or Path(filename).name != filename:
                        raise ValueError
                    sources.append({"pack_id": pack_id, "filename": filename})
                if sources:
                    normalized[digest] = sources
        except (TypeError, ValueError) as exc:
            raise ValueError("自动捕获黑名单文件损坏") from exc
        return normalized

    def _write_auto_unlocked(self, entries: dict[str, list[dict[str, str]]]) -> None:
        atomic_write_json(
            self.auto_path,
            {
                "schema_version": CAPTURE_AUTO_BLACKLIST_SCHEMA_VERSION,
                "entries": entries,
            },
        )

    def load(self) -> set[str]:
        with self._lock():
            return self._load_unlocked() | set(self._load_auto_unlocked())

    def manual_entries(self) -> set[str]:
        """Return only permanent entries written by an explicit user action."""
        with self._lock():
            return self._load_unlocked()

    def contains(self, digest: str) -> bool:
        normalized = _normalize_digest(digest)
        with self._lock():
            return normalized in self._load_unlocked() or normalized in self._load_auto_unlocked()

    def add(self, digests: set[str]) -> int:
        normalized = {_normalize_digest(value) for value in digests}
        if not normalized:
            return 0
        with self._lock():
            existing = self._load_unlocked()
            added = normalized - existing
            if not added:
                return 0
            merged = existing | normalized
            atomic_write_json(
                self.path,
                {
                    "schema_version": CAPTURE_BLACKLIST_SCHEMA_VERSION,
                    "sha256s": sorted(merged),
                },
            )
            return len(added)

    def add_auto(self, digest: str, *, pack_id: str, filename: str) -> int:
        normalized = _normalize_digest(digest)
        source_pack_id = str(pack_id or "").strip()
        source_filename = str(filename or "").strip()
        if not source_pack_id or not source_filename or Path(source_filename).name != source_filename:
            raise ValueError("自动黑名单来源无效")
        source = {"pack_id": source_pack_id, "filename": source_filename}
        with self._lock():
            entries = self._load_auto_unlocked()
            sources = entries.setdefault(normalized, [])
            if source in sources:
                return 0
            sources.append(source)
            sources.sort(key=lambda item: (item["pack_id"], item["filename"]))
            self._write_auto_unlocked(entries)
            return 1

    def auto_entries(self) -> dict[str, list[dict[str, str]]]:
        with self._lock():
            return {
                digest: [dict(source) for source in sources]
                for digest, sources in self._load_auto_unlocked().items()
            }

    def remove_auto(self, digests: set[str]) -> int:
        normalized = {_normalize_digest(value) for value in digests}
        if not normalized:
            return 0
        with self._lock():
            entries = self._load_auto_unlocked()
            removed = normalized & set(entries)
            if not removed:
                return 0
            for digest in removed:
                entries.pop(digest, None)
            self._write_auto_unlocked(entries)
            return len(removed)

    def prune_auto_sources(self, source_exists: Callable[[str, str], bool]) -> int:
        if not callable(source_exists):
            raise TypeError("source_exists 必须可调用")
        with self._lock():
            entries = self._load_auto_unlocked()
            stale = {
                digest
                for digest, sources in entries.items()
                if not any(
                    source_exists(source["pack_id"], source["filename"])
                    for source in sources
                )
            }
            if not stale:
                return 0
            for digest in stale:
                entries.pop(digest, None)
            self._write_auto_unlocked(entries)
            return len(stale)

    def reconcile_pack(self, pack_dir: Path | str) -> dict[str, int]:
        """Migrate legacy duplicate events and remove stale automatic entries."""
        pack_root = Path(pack_dir).resolve()
        pack_roots = {
            path.name: path
            for path in pack_root.parent.iterdir()
            if path.is_dir()
        }

        def source_exists(pack_id: str, filename: str) -> bool:
            source_root = pack_roots.get(pack_id)
            return bool(source_root and (source_root / "memes" / filename).is_file())

        pruned = self.prune_auto_sources(source_exists)
        try:
            from .capture_activity import (
                load_capture_activity,
                mark_capture_events_blacklisted,
            )
        except ImportError:
            from capture_activity import load_capture_activity, mark_capture_events_blacklisted

        duplicate_digests: set[str] = set()
        for event in load_capture_activity(pack_root).get("events", []):
            if not isinstance(event, dict) or event.get("status") != "duplicate":
                continue
            digest = str(event.get("sha256") or "").strip().lower()
            filename = str(event.get("filename") or "").strip()
            if not _DIGEST_PATTERN.fullmatch(digest) or not filename:
                continue
            if Path(filename).name != filename or not source_exists(pack_root.name, filename):
                continue
            self.add_auto(digest, pack_id=pack_root.name, filename=filename)
            duplicate_digests.add(digest)
        blacklisted_events = mark_capture_events_blacklisted(
            pack_root,
            digests=duplicate_digests,
        )
        return {
            "pruned": pruned,
            "migrated": len(duplicate_digests),
            "blacklisted_events": blacklisted_events,
        }

    def run_if_allowed(self, digest: str, operation: Callable[[], T]) -> tuple[bool, T | None]:
        normalized = _normalize_digest(digest)
        if not callable(operation):
            raise TypeError("operation 必须可调用")
        with self._lock():
            if normalized in self._load_unlocked() or normalized in self._load_auto_unlocked():
                return False, None
            return True, operation()
