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
        self.path = Path(plugin_data_dir).resolve() / CAPTURE_BLACKLIST_FILENAME

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

    def load(self) -> set[str]:
        with self._lock():
            return self._load_unlocked()

    def contains(self, digest: str) -> bool:
        normalized = _normalize_digest(digest)
        with self._lock():
            return normalized in self._load_unlocked()

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

    def run_if_allowed(self, digest: str, operation: Callable[[], T]) -> tuple[bool, T | None]:
        normalized = _normalize_digest(digest)
        if not callable(operation):
            raise TypeError("operation 必须可调用")
        with self._lock():
            if normalized in self._load_unlocked():
                return False, None
            return True, operation()
