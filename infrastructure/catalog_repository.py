"""Catalog boundary and cross-thread/process locking."""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any


class CatalogLock:
    """Serialize one catalog path in-process and with an advisory OS lock."""

    _locks: defaultdict[str, threading.RLock] = defaultdict(threading.RLock)

    def __init__(self, path: Path | str):
        self.path = Path(path).resolve()
        self._thread_lock = self._locks[str(self.path)]
        self._handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock.acquire()
        self._handle = self.path.open("a+b")
        self._handle.seek(0, os.SEEK_END)
        if self._handle.tell() == 0:
            self._handle.write(b"0")
            self._handle.flush()
        self._handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._handle is not None:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
        self._thread_lock.release()


class CatalogRepository:
    """Stable catalog API backed by the existing MemeStore implementation."""

    def __init__(self, root: Path | str, *, store: Any | None = None):
        if store is None:
            try:
                from ..storage import MemeStore
            except ImportError:
                from storage import MemeStore

            store = MemeStore(Path(root))
        self.store = store
        self.root = Path(getattr(store, "root", root)).resolve()
        self.lock_path = self.root / "memes" / ".catalog.lock"

    def load(self, category: str | None = None) -> dict[str, Any]:
        return self.store.load_catalog(category)

    def write(
        self,
        entries: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with CatalogLock(self.lock_path):
            self.store.write_catalog(entries, metadata=metadata)

    def reconcile(self) -> int:
        with CatalogLock(self.lock_path):
            return int(self.store.reconcile_catalogs())

    def rebuild_tag_index(self) -> dict[str, Any]:
        with CatalogLock(self.lock_path):
            return self.store.rebuild_tag_index()
