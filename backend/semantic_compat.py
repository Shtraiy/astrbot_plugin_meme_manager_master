"""Lazy compatibility bridge for retired semantic features.

Core startup imports this module, but the heavy semantic implementation is
loaded only when a caller explicitly requests a semantic operation.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

try:
    from ..domain.category_mapping import runtime_category_mapping
except ImportError:  # standalone test imports from repository root
    from domain.category_mapping import runtime_category_mapping

REVIEW_CATEGORY = "needs_review"


def _module(name: str):
    return importlib.import_module(f"{__package__}.{name}")


def _semantic_models():
    return _module("semantic_models")


def _semantic_query():
    return _module("semantic_query")


def _semantic_storage():
    return _module("semantic_storage")


def _semantic_index():
    return _module("semantic_index")


def compact_semantic_query(value: Any, max_chars: int = 160) -> str:
    try:
        return _semantic_models().compact_semantic_query(value, max_chars)
    except Exception:
        query = re.sub(r"\s+", " ", str(value or "")).strip()
        return query[: max(8, int(max_chars or 160))].rstrip(" ,.;，。；")


def extract_and_clean_semantic_meme_references(text: str) -> tuple[str, list[str]]:
    try:
        return _semantic_models().extract_and_clean_semantic_meme_references(text)
    except Exception:
        return str(text or "").strip(), []


def extract_visible_semantic_reply(text: str) -> str:
    try:
        return _semantic_models().extract_visible_semantic_reply(text)
    except Exception:
        return str(text or "").strip()


def parse_semantic_query_result(value: Any, fallback: str = "") -> str:
    try:
        return _semantic_models().parse_semantic_query_result(value, fallback)
    except Exception:
        return compact_semantic_query(value or fallback)


async def search_memes(*args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return await _semantic_query().search_memes(*args, **kwargs)
    except Exception as exc:
        return {"ok": False, "candidates": [], "reason": str(exc) or "semantic unavailable"}


def candidate_records(pack_dir: Path | str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        return _semantic_query().candidate_records(pack_dir, candidates)
    except Exception:
        return []


def remember_candidates(event: Any, candidates: list[dict[str, Any]]) -> None:
    try:
        _semantic_query().remember_candidates(event, candidates)
    except Exception:
        return None


def validate_selected_id(event: Any, value: str, pack_dir: Path | str) -> Path | None:
    try:
        return _semantic_query().validate_selected_id(event, value, pack_dir)
    except Exception:
        return None


def invalidate_semantic_metadata(pack_dir: Path | str) -> dict[str, Any]:
    try:
        return _semantic_storage().invalidate_semantic_metadata(pack_dir)
    except Exception:
        return {"removed": False, "reason": "semantic unavailable"}


LEGACY_METADATA_BACKUP_NAME = "semantic_metadata.pre-v2.backup.json"


def get_pack_semantic_summary(pack_dir: Path | str, image_count: int = 0) -> dict[str, Any]:
    try:
        return _semantic_storage().get_pack_semantic_summary(pack_dir, image_count)
    except Exception:
        return {
            "semantic_metadata": False,
            "semantic_done": 0,
            "semantic_total": int(image_count or 0),
            "vectors": False,
        }


def import_metadata_file(path: Path | str) -> dict[str, Any]:
    try:
        return _semantic_storage().import_metadata_file(path)
    except Exception:
        return {}


def load_metadata(pack_dir: Path | str) -> dict[str, Any]:
    try:
        return _semantic_storage().load_metadata(pack_dir)
    except Exception:
        return {}


def reconcile_metadata(*args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return _semantic_storage().reconcile_metadata(*args, **kwargs)
    except Exception:
        return {}


def reset_local_embedding_state(data: Any) -> Any:
    try:
        return _semantic_storage().reset_local_embedding_state(data)
    except Exception:
        return data


def save_metadata(*args: Any, **kwargs: Any) -> Any:
    try:
        return _semantic_storage().save_metadata(*args, **kwargs)
    except Exception:
        return None


def index_is_ready(*args: Any, **kwargs: Any) -> bool:
    try:
        return bool(_semantic_index().index_is_ready(*args, **kwargs))
    except Exception:
        return False


def load_index_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        value = _semantic_index().load_index_manifest(*args, **kwargs)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}
