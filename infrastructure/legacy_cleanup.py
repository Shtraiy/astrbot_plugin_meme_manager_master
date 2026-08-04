"""Narrow cleanup for retired semantic artifacts."""

from __future__ import annotations

import shutil
from pathlib import Path


def cleanup_legacy_semantic_data(plugin_data_dir: Path | str) -> int:
    root = Path(plugin_data_dir).resolve()
    removed = 0
    packs_root = root / "packs"
    if packs_root.is_dir():
        for metadata_path in packs_root.rglob("semantic_metadata.json"):
            if not metadata_path.is_file() or metadata_path.is_symlink():
                continue
            try:
                metadata_path.unlink()
                removed += 1
            except OSError:
                continue

    semantic_indexes = root / "semantic_indexes"
    if semantic_indexes.is_dir() and not semantic_indexes.is_symlink():
        try:
            shutil.rmtree(semantic_indexes)
            removed += 1
        except OSError:
            pass
    return removed
