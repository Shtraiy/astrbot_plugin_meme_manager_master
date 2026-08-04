"""Filesystem implementation of the stable PackResolver port."""

from __future__ import annotations

from pathlib import Path

try:
    from ..domain.models import PackContext, PackId
except ImportError:  # standalone test imports from repository root
    from domain.models import PackContext, PackId


class FilesystemPackResolver:
    def __init__(self, packs_root: Path | str, *, require_exists: bool = False):
        self.packs_root = Path(packs_root).resolve()
        self.require_exists = bool(require_exists)

    def resolve(self, pack_id: str) -> PackContext:
        normalized = PackId(pack_id)
        root = (self.packs_root / normalized.value).resolve()
        try:
            root.relative_to(self.packs_root)
        except ValueError as exc:
            raise ValueError("pack path escapes packs root") from exc
        if self.require_exists and not root.is_dir():
            raise FileNotFoundError(f"pack does not exist: {normalized.value}")
        return PackContext(normalized, root, self.packs_root)
