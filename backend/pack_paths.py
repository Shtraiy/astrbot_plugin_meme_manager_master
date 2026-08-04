"""Bounded path operations for pack and backup storage."""

from __future__ import annotations

import re
from pathlib import Path


_PACK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


class PackPaths:
    def __init__(self, packs_root: Path | str, backup_root: Path | str):
        self.packs_root = Path(packs_root)
        self.backup_root = Path(backup_root)

    @staticmethod
    def _validate_pack_id(pack_id: str) -> str:
        value = str(pack_id or "").strip()
        if not _PACK_ID.fullmatch(value) or value in {".", ".."}:
            raise ValueError("invalid pack id")
        return value

    @staticmethod
    def _validate_filename(filename: str) -> str:
        value = str(filename or "").strip()
        if not value or Path(value).name != value or value in {".", ".."}:
            raise ValueError("invalid backup filename")
        return value

    @staticmethod
    def _bounded(root: Path, child: Path) -> None:
        root_resolved = root.resolve(strict=False)
        child_resolved = child.resolve(strict=False)
        try:
            child_resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError("path escapes configured root") from exc

    def pack(self, pack_id: str) -> Path:
        normalized = self._validate_pack_id(pack_id)
        target = self.packs_root / normalized
        self._bounded(self.packs_root, target)
        return target

    def backup(self, filename: str) -> Path:
        normalized = self._validate_filename(filename)
        target = self.backup_root / normalized
        self._bounded(self.backup_root, target)
        return target
