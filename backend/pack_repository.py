"""Pack-scoped transactions for category and image mutations.

Every public mutation runs under the same per-pack write lock and either
commits atomically or rolls the filesystem back, so callers never observe a
half-applied category rename/delete or a lost old image during replacement.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PIL import Image

from .atomic_io import atomic_write_json


SLOTS_SUPPORTED = sys.version_info >= (3, 10)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
TRASH_MAX_AGE_SECONDS = 24 * 3600

_LOCKS_GUARD = threading.Lock()
_PACK_LOCKS: dict[str, threading.RLock] = {}


def _frozen_dataclass(*, slots: bool = False):
    """dataclass(frozen=True) that tolerates Python 3.9 (no slots kwarg)."""
    if SLOTS_SUPPORTED:
        return dataclass(frozen=True, slots=slots)
    return dataclass(frozen=True)


def pack_lock(pack_dir: Path) -> threading.RLock:
    key = str(Path(pack_dir).resolve())
    with _LOCKS_GUARD:
        return _PACK_LOCKS.setdefault(key, threading.RLock())


@_frozen_dataclass(slots=True)
class BatchMutationResult:
    succeeded: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    conflicting: tuple[str, ...] = ()


def _is_safe_segment(value: str) -> bool:
    return bool(value) and value == value.strip() and value not in {".", ".."} and "/" not in value and "\\" not in value


def _is_safe_filename(value: str) -> bool:
    name = Path(value).name
    if not name or name != value or name in {".", ".."}:
        return False
    return name.lower().endswith(IMAGE_EXTENSIONS)


class PackRepository:
    """Transactional category/image mutations for one pack directory."""

    def __init__(self, pack_dir: Path):
        self.pack_dir = Path(pack_dir).resolve()
        self.memes_dir = self.pack_dir / "memes"
        self.metadata_path = self.pack_dir / "memes_data.json"
        self.trash_dir = self.pack_dir / ".trash"

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def load_metadata(self) -> dict[str, str]:
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save_metadata(self, metadata: dict[str, str]) -> None:
        atomic_write_json(self.metadata_path, metadata)

    def _reconcile(self, categories: Sequence[str]) -> None:
        try:
            from ..storage import MemeStore
        except ImportError:  # standalone test imports (repo root on sys.path)
            from storage import MemeStore

        try:
            MemeStore(self.pack_dir).reconcile_categories(categories)
        except Exception:
            # Index repair must never change the mutation result.
            pass

    def _invalidate_semantic(self) -> None:
        if not (self.pack_dir / "semantic_metadata.json").is_file():
            return
        try:
            from .semantic_storage import invalidate_semantic_metadata

            invalidate_semantic_metadata(self.pack_dir)
        except Exception:
            pass

    def cleanup_stale_trash(self, max_age_seconds: int = TRASH_MAX_AGE_SECONDS) -> int:
        """Remove .trash items older than the age limit (crashed transactions)."""
        removed = 0
        if not self.trash_dir.is_dir():
            return 0
        now = time.time()
        for entry in self.trash_dir.iterdir():
            try:
                if now - entry.stat().st_mtime <= max_age_seconds:
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    # ------------------------------------------------------------------
    # Category transactions
    # ------------------------------------------------------------------
    def rename_category(self, old_name: str, new_name: str) -> bool:
        with pack_lock(self.pack_dir):
            old_name = str(old_name or "").strip()
            new_name = str(new_name or "").strip()
            if not _is_safe_segment(old_name) or not _is_safe_segment(new_name):
                return False
            if old_name == new_name:
                return True
            metadata = self.load_metadata()
            old_dir = self.memes_dir / old_name
            new_dir = self.memes_dir / new_name
            if new_dir.exists() or new_name in metadata:
                return False
            if not old_dir.is_dir() and old_name not in metadata:
                return False

            renamed = False
            if old_dir.is_dir():
                os.rename(old_dir, new_dir)
                renamed = True
            try:
                new_metadata = {
                    (new_name if key == old_name else key): value
                    for key, value in metadata.items()
                }
                self.save_metadata(new_metadata)
            except Exception:
                if renamed and new_dir.is_dir():
                    os.rename(new_dir, old_dir)
                raise
            self._reconcile([new_name])
            self._invalidate_semantic()
            return True

    def delete_category(self, category: str) -> bool:
        with pack_lock(self.pack_dir):
            category = str(category or "").strip()
            if not _is_safe_segment(category):
                return False
            metadata = self.load_metadata()
            category_dir = self.memes_dir / category
            if not category_dir.is_dir() and category not in metadata:
                return False

            trash_path: Path | None = None
            if category_dir.is_dir():
                self.trash_dir.mkdir(parents=True, exist_ok=True)
                trash_path = self.trash_dir / f"category-{uuid.uuid4().hex}"
                os.rename(category_dir, trash_path)
            try:
                new_metadata = {
                    key: value for key, value in metadata.items() if key != category
                }
                self.save_metadata(new_metadata)
            except Exception:
                if trash_path is not None and trash_path.is_dir():
                    category_dir.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(trash_path, category_dir)
                raise
            if trash_path is not None and trash_path.is_dir():
                shutil.rmtree(trash_path)
            self._reconcile([])
            self._invalidate_semantic()
            return True

    # ------------------------------------------------------------------
    # Image transactions
    # ------------------------------------------------------------------
    def replace_image(
        self,
        category: str,
        old_name: str,
        new_name: str,
        content: bytes,
    ) -> Path:
        """Atomically replace one image; the old file survives every failure."""
        with pack_lock(self.pack_dir):
            category = str(category or "").strip()
            old_name = str(old_name or "")
            new_name = str(new_name or "")
            if not _is_safe_segment(category):
                raise ValueError(f"invalid category name: {category!r}")
            if not _is_safe_filename(old_name) or not _is_safe_filename(new_name):
                raise ValueError("unsupported image filename or extension")
            if not content:
                raise ValueError("empty image content")
            if len(content) > MAX_IMAGE_BYTES:
                raise ValueError("image content exceeds size limit")
            category_dir = self.memes_dir / category
            if not category_dir.is_dir():
                raise FileNotFoundError(f"category not found: {category}")
            old_path = category_dir / old_name
            if not old_path.is_file():
                raise FileNotFoundError(f"image not found: {old_name}")
            target_path = category_dir / new_name
            if target_path != old_path and target_path.exists():
                raise FileExistsError(f"target image already exists: {new_name}")

            fd, temp_name = tempfile.mkstemp(
                prefix=f".{new_name}.", suffix=".tmp", dir=category_dir
            )
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                with Image.open(temp_name) as image:
                    image.verify()
                os.replace(temp_name, target_path)
            except Exception:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
            if target_path != old_path:
                old_path.unlink(missing_ok=True)
            self._reconcile([category])
            self._invalidate_semantic()
            return target_path

    # ------------------------------------------------------------------
    # Batch image transactions (one reconcile per affected category)
    # ------------------------------------------------------------------
    def move_images(
        self,
        source: str,
        target: str,
        filenames: Sequence[str],
    ) -> BatchMutationResult:
        with pack_lock(self.pack_dir):
            source = str(source or "").strip()
            target = str(target or "").strip()
            if not _is_safe_segment(source) or not _is_safe_segment(target):
                raise ValueError("invalid category name")
            source_dir = self.memes_dir / source
            if not source_dir.is_dir():
                return BatchMutationResult()
            target_dir = self.memes_dir / target
            target_dir.mkdir(parents=True, exist_ok=True)
            succeeded: list[str] = []
            missing: list[str] = []
            conflicting: list[str] = []
            for raw in dict.fromkeys(str(item) for item in filenames):
                name = Path(raw).name
                if not _is_safe_filename(name):
                    missing.append(name)
                    continue
                source_path = source_dir / name
                target_path = target_dir / name
                if not source_path.is_file():
                    missing.append(name)
                elif target_path.exists():
                    conflicting.append(name)
                else:
                    os.rename(source_path, target_path)
                    succeeded.append(name)
            self._reconcile([source, target])
            self._invalidate_semantic()
            return BatchMutationResult(
                tuple(succeeded), tuple(missing), tuple(conflicting)
            )

    def copy_images(
        self,
        source: str,
        target: str,
        filenames: Sequence[str],
    ) -> BatchMutationResult:
        with pack_lock(self.pack_dir):
            source = str(source or "").strip()
            target = str(target or "").strip()
            if not _is_safe_segment(source) or not _is_safe_segment(target):
                raise ValueError("invalid category name")
            source_dir = self.memes_dir / source
            if not source_dir.is_dir():
                return BatchMutationResult()
            target_dir = self.memes_dir / target
            target_dir.mkdir(parents=True, exist_ok=True)
            succeeded: list[str] = []
            missing: list[str] = []
            conflicting: list[str] = []
            for raw in dict.fromkeys(str(item) for item in filenames):
                name = Path(raw).name
                if not _is_safe_filename(name):
                    missing.append(name)
                    continue
                source_path = source_dir / name
                target_path = target_dir / name
                if not source_path.is_file():
                    missing.append(name)
                elif target_path.exists():
                    conflicting.append(name)
                else:
                    shutil.copy2(source_path, target_path)
                    succeeded.append(name)
            self._reconcile([source, target])
            self._invalidate_semantic()
            return BatchMutationResult(
                tuple(succeeded), tuple(missing), tuple(conflicting)
            )

    def delete_images(
        self,
        category: str,
        filenames: Sequence[str],
    ) -> BatchMutationResult:
        with pack_lock(self.pack_dir):
            category = str(category or "").strip()
            if not _is_safe_segment(category):
                raise ValueError("invalid category name")
            category_dir = self.memes_dir / category
            if not category_dir.is_dir():
                return BatchMutationResult()
            succeeded: list[str] = []
            missing: list[str] = []
            for raw in dict.fromkeys(str(item) for item in filenames):
                name = Path(raw).name
                if not _is_safe_filename(name):
                    missing.append(name)
                    continue
                image_path = category_dir / name
                if not image_path.is_file():
                    missing.append(name)
                else:
                    image_path.unlink()
                    succeeded.append(name)
            self._reconcile([category])
            self._invalidate_semantic()
            return BatchMutationResult(tuple(succeeded), tuple(missing))
