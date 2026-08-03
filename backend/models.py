"""Compatibility API for flat meme storage and controlled tags."""

from __future__ import annotations

import logging
from pathlib import Path

from werkzeug.utils import secure_filename

from ..config import MEMES_DIR, get_active_pack_paths
from ..storage import IMAGE_EXTENSIONS, MemeStore, detect_image_extension
from .tagging import canonical_tag, normalize_tags

logger = logging.getLogger(__name__)
MAX_UPLOAD_IMAGE_BYTES = 10 * 1024 * 1024


class DuplicateEmojiError(ValueError):
    """Kept for callers that still import the legacy exception."""

    def __init__(self, existing_filename: str):
        self.existing_filename = existing_filename
        super().__init__(f"duplicate meme: {existing_filename}")


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


def _find_item(store: MemeStore, filename: str) -> dict | None:
    return next(
        (item for item in _catalog_items(store) if item.get("filename") == filename),
        None,
    )


def _mutate_tags(
    filename: str,
    memes_dir: str | Path | None,
    *,
    add: object = None,
    remove: object = None,
) -> bool:
    store = _store_for(memes_dir)
    name = _image_name(filename)
    target = _tag(add) if add is not None else None
    source = _tag(remove) if remove is not None else None
    if not name or not (store.memes_dir / name).is_file():
        return False
    items = _catalog_items(store)
    changed = False
    for item in items:
        if item.get("filename") != name:
            continue
        tags = list(item.get("tags") or [])
        if source in tags:
            tags.remove(source)
            changed = True
        if target and target not in tags:
            tags = normalize_tags([*tags, target])
            changed = True
        item["tags"] = normalize_tags(tags)
        break
    if not changed:
        return False
    _write_items(store, items)
    return True


async def scan_emoji_folder(memes_dir: str | Path | None = None):
    """Return virtual tag buckets backed by the single flat catalog."""
    store = _store_for(memes_dir)
    result: dict[str, list[str]] = {}
    for item in _catalog_items(store):
        filename = _image_name(item.get("filename"))
        if not filename or not (store.memes_dir / filename).is_file():
            continue
        for tag in item.get("tags", []):
            result.setdefault(tag, []).append(filename)
    return {tag: sorted(set(names)) for tag, names in sorted(result.items())}


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


def add_emoji_to_category(category, image_file, memes_dir: str | Path | None = None):
    """Validate an upload and add its canonical tag to a flat meme entry."""
    if not image_file or not getattr(image_file, "filename", ""):
        raise ValueError("upload file is required")
    tag = _tag(category)
    if not tag:
        raise ValueError("invalid meme tag")
    filename = secure_filename(str(image_file.filename))
    if not filename or Path(filename).suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("unsupported image extension")
    stream = getattr(image_file, "stream", image_file)
    try:
        stream.seek(0)
    except (AttributeError, OSError):
        pass
    content = stream.read(MAX_UPLOAD_IMAGE_BYTES + 1)
    if not content:
        raise ValueError("uploaded image is empty")
    if len(content) > MAX_UPLOAD_IMAGE_BYTES:
        raise ValueError("uploaded image exceeds 10 MB")
    detected = detect_image_extension(content)
    suffix = Path(filename).suffix.lower()
    expected = {suffix}
    if suffix in {".jpg", ".jpeg"}:
        expected = {".jpg", ".jpeg"}
    if detected is None or detected not in expected:
        raise ValueError("image content does not match its extension")

    store = _store_for(memes_dir)
    result = store.save_image(content, [tag], Path(filename).suffix.lower())
    return {
        "path": str(result.path),
        "filename": result.path.name,
        "tags": _find_item(store, result.path.name).get("tags", [tag]),
        "duplicate": result.status == "duplicate",
    }


def delete_emoji_from_category(category, image_file, memes_dir: str | Path | None = None):
    """Delete one flat meme file, regardless of the selected virtual tag."""
    store = _store_for(memes_dir)
    name = _image_name(image_file)
    path = store.memes_dir / name
    if not name or not path.is_file():
        return False
    path.unlink()
    _write_items(store, [item for item in _catalog_items(store) if item.get("filename") != name])
    return True


def batch_delete_emojis(category, image_files, memes_dir: str | Path | None = None):
    store = _store_for(memes_dir)
    names = [_image_name(value) for value in image_files]
    deleted = [name for name in names if name and delete_emoji_from_category(category, name, memes_dir)]
    return {
        "category_exists": bool(_tag(category) and get_emoji_by_category(category, memes_dir)),
        "deleted_files": deleted,
        "missing_files": [name for name in names if name and name not in deleted],
    }


def move_emoji_to_category(source_category, image_file, target_category, memes_dir=None):
    source = _tag(source_category)
    target = _tag(target_category)
    name = _image_name(image_file)
    exists = bool(source and get_emoji_by_category(source, memes_dir))
    base = {
        "source_category_exists": exists,
        "source_category": source_category,
        "target_category": target_category,
        "filename": name,
    }
    if not source or not target or name not in get_emoji_by_category(source, memes_dir):
        return {**base, "moved": False, "conflict": False, "missing": True}
    return {**base, "moved": _mutate_tags(name, memes_dir, add=target, remove=source), "conflict": False, "missing": False}


def batch_move_emojis(source_category, image_files, target_category, memes_dir=None):
    moved, missing = [], []
    for name in image_files:
        result = move_emoji_to_category(source_category, name, target_category, memes_dir)
        (moved if result["moved"] else missing).append(Path(str(name)).name)
    return {
        "source_category_exists": bool(_tag(source_category) and get_emoji_by_category(source_category, memes_dir)),
        "source_category": source_category,
        "target_category": target_category,
        "moved_files": moved,
        "missing_files": missing,
        "conflicting_files": [],
    }


def copy_emoji_to_category(source_category, image_file, target_category, memes_dir=None):
    source = _tag(source_category)
    target = _tag(target_category)
    name = _image_name(image_file)
    source_names = get_emoji_by_category(source, memes_dir) if source else []
    base = {
        "source_category_exists": bool(source_names),
        "source_category": source_category,
        "target_category": target_category,
        "filename": name,
    }
    if name not in source_names or not target:
        return {**base, "copied": False, "conflict": False, "missing": True}
    return {**base, "copied": _mutate_tags(name, memes_dir, add=target), "conflict": False, "missing": False}


def batch_copy_emojis(source_category, image_files, target_category, memes_dir=None):
    copied, missing = [], []
    for name in image_files:
        result = copy_emoji_to_category(source_category, name, target_category, memes_dir)
        (copied if result["copied"] else missing).append(Path(str(name)).name)
    return {
        "source_category_exists": bool(_tag(source_category) and get_emoji_by_category(source_category, memes_dir)),
        "source_category": source_category,
        "target_category": target_category,
        "copied_files": copied,
        "missing_files": missing,
        "conflicting_files": [],
    }


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


def update_emoji_in_category(category, old_image_file, new_image_file, memes_dir=None):
    """Replace one image while preserving its current tag set."""
    old_name = _image_name(old_image_file)
    if not old_name:
        return False
    result = add_emoji_to_category(category, new_image_file, memes_dir)
    if result["filename"] != old_name:
        delete_emoji_from_category(category, old_name, memes_dir)
    return True
