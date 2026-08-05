"""Lazy compatibility bridge for retired semantic features.

Core startup imports this module, but the heavy semantic implementation is
loaded only when a caller explicitly requests a semantic operation.
"""

from __future__ import annotations

import importlib
import logging
import re
from pathlib import Path
from typing import Any

try:
    from ..domain.category_mapping import runtime_category_mapping
except ImportError:  # standalone test imports from repository root
    from domain.category_mapping import runtime_category_mapping

REVIEW_CATEGORY = "needs_review"
logger = logging.getLogger(__name__)
_last_diagnostic = ""


def _diagnose(operation: str, exc: Exception) -> str:
    """Record why an optional semantic call degraded without changing its contract."""
    global _last_diagnostic
    kind = "unavailable" if isinstance(exc, ImportError) else "runtime failure"
    detail = str(exc).strip() or exc.__class__.__name__
    _last_diagnostic = f"semantic {kind} during {operation}: {detail}"
    logger.warning("%s", _last_diagnostic, exc_info=kind == "runtime failure")
    return _last_diagnostic


def last_semantic_diagnostic() -> str:
    """Return the latest optional-semantic failure for health checks and support."""
    return _last_diagnostic


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
    except Exception as exc:
        _diagnose("compact query", exc)
        query = re.sub(r"\s+", " ", str(value or "")).strip()
        return query[: max(8, int(max_chars or 160))].rstrip(" ,.;，。；")


def extract_and_clean_semantic_meme_references(text: str) -> tuple[str, list[str]]:
    try:
        return _semantic_models().extract_and_clean_semantic_meme_references(text)
    except Exception as exc:
        _diagnose("extract meme references", exc)
        return str(text or "").strip(), []


def extract_visible_semantic_reply(text: str) -> str:
    try:
        return _semantic_models().extract_visible_semantic_reply(text)
    except Exception as exc:
        _diagnose("extract visible reply", exc)
        return str(text or "").strip()


def parse_semantic_query_result(value: Any, fallback: str = "") -> str:
    try:
        return _semantic_models().parse_semantic_query_result(value, fallback)
    except Exception as exc:
        _diagnose("parse query result", exc)
        return compact_semantic_query(value or fallback)


async def search_memes(*args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return await _semantic_query().search_memes(*args, **kwargs)
    except Exception as exc:
        return {"ok": False, "candidates": [], "reason": _diagnose("search", exc)}


def candidate_records(pack_dir: Path | str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        return _semantic_query().candidate_records(pack_dir, candidates)
    except Exception as exc:
        _diagnose("candidate records", exc)
        return []


def remember_candidates(event: Any, candidates: list[dict[str, Any]]) -> None:
    try:
        _semantic_query().remember_candidates(event, candidates)
    except Exception as exc:
        _diagnose("remember candidates", exc)
        return None


def validate_selected_id(event: Any, value: str, pack_dir: Path | str) -> Path | None:
    try:
        return _semantic_query().validate_selected_id(event, value, pack_dir)
    except Exception as exc:
        _diagnose("validate selected id", exc)
        return None


def invalidate_semantic_metadata(pack_dir: Path | str) -> dict[str, Any]:
    try:
        return _semantic_storage().invalidate_semantic_metadata(pack_dir)
    except Exception as exc:
        return {"removed": False, "reason": _diagnose("invalidate metadata", exc)}


LEGACY_METADATA_BACKUP_NAME = "semantic_metadata.pre-v2.backup.json"


def get_pack_semantic_summary(pack_dir: Path | str, image_count: int = 0) -> dict[str, Any]:
    try:
        return _semantic_storage().get_pack_semantic_summary(pack_dir, image_count)
    except Exception as exc:
        _diagnose("get pack summary", exc)
        return {
            "semantic_metadata": False,
            "semantic_done": 0,
            "semantic_total": int(image_count or 0),
            "vectors": False,
        }


def import_metadata_file(path: Path | str) -> dict[str, Any]:
    try:
        return _semantic_storage().import_metadata_file(path)
    except Exception as exc:
        _diagnose("import metadata", exc)
        return {}


def load_metadata(pack_dir: Path | str) -> dict[str, Any]:
    try:
        return _semantic_storage().load_metadata(pack_dir)
    except Exception as exc:
        _diagnose("load metadata", exc)
        return {}


def reconcile_metadata(*args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return _semantic_storage().reconcile_metadata(*args, **kwargs)
    except Exception as exc:
        _diagnose("reconcile metadata", exc)
        return {}


def reset_local_embedding_state(data: Any) -> Any:
    try:
        return _semantic_storage().reset_local_embedding_state(data)
    except Exception as exc:
        _diagnose("reset embedding state", exc)
        return data


def save_metadata(*args: Any, **kwargs: Any) -> Any:
    try:
        return _semantic_storage().save_metadata(*args, **kwargs)
    except Exception as exc:
        _diagnose("save metadata", exc)
        return None


def index_is_ready(*args: Any, **kwargs: Any) -> bool:
    try:
        return bool(_semantic_index().index_is_ready(*args, **kwargs))
    except Exception as exc:
        _diagnose("check index readiness", exc)
        return False


def load_index_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        value = _semantic_index().load_index_manifest(*args, **kwargs)
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        _diagnose("load index manifest", exc)
        return {}
