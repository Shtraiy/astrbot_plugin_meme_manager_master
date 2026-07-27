"""Helpers for correlating multimodal library-index results with files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def catalog_needs_write(
    catalog: dict[str, Any],
    entries: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> bool:
    """Return whether writing the generated index would change its content."""
    return catalog.get("items") != entries or any(
        catalog.get(key) != value for key, value in metadata.items()
    )


def normalize_library_results(
    items: Any,
    image_paths: list[Path],
) -> dict[Path, dict[str, Any]]:
    """Normalize model output while keeping file/result associations safe.

    Models commonly return the requested id, a filename, or no id at all.
    Filename matching is unambiguous; positional matching is only used when
    the response contains one result per input image.
    """
    if isinstance(items, dict):
        if all(isinstance(value, dict) for value in items.values()):
            items = [dict(value, id=key) for key, value in items.items()]
        else:
            items = [items]
    if not isinstance(items, list):
        raise ValueError("batch model response items is not a list")

    valid_items = [item for item in items if isinstance(item, dict)]
    expected_ids = {f"image_{index}": path for index, path in enumerate(image_paths)}
    numeric_ids = {
        int(match.group(1))
        for item in valid_items
        if (match := re.fullmatch(r"(?:image|img)[_-]?(\d+)", str(item.get("id", ""))))
    }
    if len(valid_items) == len(image_paths) and numeric_ids == set(
        range(1, len(image_paths) + 1)
    ):
        expected_ids = {
            f"image_{index + 1}": path
            for index, path in enumerate(image_paths)
        }
    by_name = {}
    for path in image_paths:
        by_name[path.name.casefold()] = path
        by_name[path.stem.casefold()] = path

    matched: dict[Path, dict[str, Any]] = {}
    used: set[int] = set()
    for item_index, item in enumerate(valid_items):
        raw_id = str(item.get("id", "") or "").strip()
        path = expected_ids.get(raw_id)
        if path is None and raw_id:
            identifier = Path(raw_id).name.casefold()
            path = by_name.get(identifier) or by_name.get(Path(identifier).stem)
        if path is None:
            continue
        if path in matched:
            used.add(item_index)
            continue
        matched[path] = _normalized_item(item)
        used.add(item_index)

    if len(valid_items) == len(image_paths):
        unmatched_paths = [path for path in image_paths if path not in matched]
        unmatched_items = [
            item for index, item in enumerate(valid_items) if index not in used
        ]
        for path, item in zip(unmatched_paths, unmatched_items):
            matched[path] = _normalized_item(item)

    return matched


def _normalized_item(item: dict[str, Any]) -> dict[str, Any]:
    tags = item.get("tags", [])
    if isinstance(tags, str):
        tags = [part.strip() for part in re.split(r"[,，、]", tags) if part.strip()]
    if not isinstance(tags, list):
        tags = []
    return {
        "description": str(item.get("description", "") or "")[:120],
        "emotion": str(item.get("emotion", "") or "")[:40],
        "text": str(item.get("text", "") or "")[:120],
        "tags": [str(tag)[:30] for tag in tags[:8] if str(tag).strip()],
        "indexed": True,
    }
