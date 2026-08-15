"""Helpers for correlating multimodal library-index results with files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from .backend.tagging import (
        normalize_primary_category,
        normalize_semantic_tags,
        normalize_tags,
    )
except ImportError:
    from backend.tagging import normalize_primary_category, normalize_semantic_tags, normalize_tags


def catalog_needs_write(
    catalog: dict[str, Any],
    entries: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> bool:
    """Return whether writing the generated index would change its content."""
    return catalog.get("items") != entries or any(
        catalog.get(key) != value for key, value in metadata.items()
    )


def full_reindex_entry_is_current(
    entry: dict[str, Any],
    digest: str,
    *,
    index_version: int,
    prompt_version: str,
) -> bool:
    """Return whether one catalog entry already satisfies the v4 contract."""
    if not isinstance(entry, dict):
        return False
    if not entry.get("indexed"):
        return False
    if entry.get("index_version") != index_version:
        return False
    if entry.get("index_prompt_version") != prompt_version:
        return False
    if entry.get("sha256") != digest:
        return False
    previous_digest = str(entry.get("reindex_previous_sha256") or "")
    if previous_digest and previous_digest != digest:
        return False
    if not normalize_primary_category(entry.get("primary_category")):
        return False
    if entry.get("primary_category_status") == "needs_reindex":
        return False

    required_fields = (
        "semantic_summary",
        "visible_text",
        "text_meaning",
        "use_cases",
        "avoid_cases",
        "classification_confidence",
        "semantic_tags",
    )
    if any(field not in entry for field in required_fields):
        return False
    if not isinstance(entry.get("semantic_summary"), str) or not entry[
        "semantic_summary"
    ].strip():
        return False
    if not isinstance(entry.get("visible_text"), str):
        return False
    if not isinstance(entry.get("text_meaning"), str):
        return False
    if not isinstance(entry.get("use_cases"), (str, list, tuple, type(None))):
        return False
    if not isinstance(entry.get("avoid_cases"), (str, list, tuple, type(None))):
        return False
    if not isinstance(entry.get("semantic_tags"), (str, list, tuple, type(None))):
        return False
    confidence = entry.get("classification_confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return False
    return 0.0 <= float(confidence) <= 1.0


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
    raw_primary = item.get("primary_category")
    if raw_primary not in (None, ""):
        primary_category = normalize_primary_category(raw_primary) or ""
        primary_status = "ready" if primary_category else "needs_reindex"
    else:
        category = normalize_primary_category(item.get("category"))
        candidates = {
            candidate
            for tag in tags
            if (candidate := normalize_primary_category(tag))
        }
        if category:
            primary_category, primary_status = category, "ready"
        elif len(candidates) == 1:
            primary_category, primary_status = next(iter(candidates)), "ready"
        else:
            primary_category, primary_status = "", "needs_reindex"
    visible_text = str(item.get("visible_text") or item.get("text") or "")[:120]
    description = str(item.get("description", "") or "")[:120]

    def text_list(value: Any) -> list[str]:
        if isinstance(value, str):
            values = re.split(r"[\r\n,，、;；]+", value)
        elif isinstance(value, list):
            values = value
        else:
            values = []
        result: list[str] = []
        for raw in values:
            text = str(raw or "").strip()
            if text and text not in result:
                result.append(text[:80])
        return result[:6]

    confidence = item.get("classification_confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = None
    return {
        "primary_category": primary_category,
        "primary_category_status": primary_status,
        "semantic_tags": normalize_semantic_tags(item.get("semantic_tags")),
        "semantic_summary": str(item.get("semantic_summary") or description)[:160],
        "description": description,
        "emotion": str(item.get("emotion", "") or "")[:40],
        "visible_text": visible_text,
        "text": visible_text,
        "text_meaning": str(item.get("text_meaning", "") or "")[:200],
        "use_cases": text_list(item.get("use_cases")),
        "avoid_cases": text_list(item.get("avoid_cases")),
        "classification_confidence": confidence,
        "tags": [str(tag)[:30] for tag in tags[:8] if str(tag).strip()],
        "indexed": True,
    }
