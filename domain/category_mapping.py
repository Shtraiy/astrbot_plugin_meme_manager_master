"""Category description normalization independent of semantic search."""

from __future__ import annotations

from collections.abc import Mapping


def runtime_category_mapping(mapping: object) -> dict[str, str]:
    """Return a stable string-to-string category description mapping."""
    if not isinstance(mapping, Mapping):
        return {}
    result: dict[str, str] = {}
    for category, description in mapping.items():
        key = str(category or "").strip()
        if not key:
            continue
        if isinstance(description, Mapping):
            description = description.get("description", "")
        result[key] = str(description or "").strip()
    return result
