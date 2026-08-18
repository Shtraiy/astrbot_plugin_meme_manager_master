"""Compatibility API for flat meme storage and controlled tags."""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import MEMES_DIR, get_active_pack_paths
from ..storage import IMAGE_EXTENSIONS, MemeStore
from .tagging import canonical_tag, normalize_tags

logger = logging.getLogger(__name__)


def _default_memes_dir() -> Path:
    try:
        return Path(get_active_pack_paths()["memes_dir"]).resolve()
    except Exception:
        return Path(MEMES_DIR).resolve()


def _memes_path(memes_dir: str | Path | None = None) -> Path:
    return Path(memes_dir or _default_memes_dir()).resolve()


def _store_for(memes_dir: str | Path | None = None) -> MemeStore:
    memes_root = _memes_path(memes_dir)
    return MemeStore(memes_root.parent)


def _tag(value: object) -> str | None:
    return canonical_tag(value)


def _image_name(value: object) -> str:
    name = Path(str(value or "")).name
    if name != str(value or "") or Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
        return ""
    return name


def _catalog_items(store: MemeStore) -> list[dict]:
    store.reindex_flat_catalog()
    return [item for item in store.load_catalog().get("items", []) if isinstance(item, dict)]


def _write_items(store: MemeStore, items: list[dict]) -> None:
    metadata = {
        key: value
        for key, value in store.load_catalog().items()
        if key not in {"version", "updated_at", "items"}
    }
    store.write_catalog(items, metadata)


def get_emoji_by_category(category, memes_dir: str | Path | None = None):
    """Read a virtual tag bucket; the old category name remains an alias."""
    tag = _tag(category)
    if not tag:
        return []
    store = _store_for(memes_dir)
    return sorted(
        item["filename"]
        for item in _catalog_items(store)
        if tag in item.get("tags", [])
        and _image_name(item.get("filename"))
        and (store.memes_dir / item["filename"]).is_file()
    )


def clear_category_emojis(category, memes_dir=None):
    """Remove a tag from matching entries while retaining the image files."""
    tag = _tag(category)
    store = _store_for(memes_dir)
    items = _catalog_items(store)
    affected = []
    for item in items:
        if tag and tag in item.get("tags", []):
            tags = [value for value in item["tags"] if value != tag]
            item["tags"] = normalize_tags(tags)
            affected.append(item["filename"])
    if affected:
        _write_items(store, items)
    return {"category_exists": bool(affected), "deleted_files": affected, "untagged_files": affected}


def clear_all_emojis(memes_dir=None):
    store = _store_for(memes_dir)
    items = _catalog_items(store)
    deleted = []
    for path in store.image_paths():
        try:
            path.unlink()
            deleted.append(path.name)
        except OSError:
            logger.warning("unable to delete meme: %s", path)
    _write_items(store, [])
    return {"deleted_by_category": {"全部": len(deleted)} if deleted else {}, "deleted_files": deleted}
