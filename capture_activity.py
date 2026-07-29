"""Small, pack-local records for the semantic capture workspace."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


CAPTURE_ACTIVITY_FILENAME = "capture_activity.json"
CAPTURE_ACTIVITY_VERSION = 1
MAX_CAPTURE_ACTIVITY_ITEMS = 500
INDEX_COMPLETION_MARKER = "classification_index_complete"


def _path(pack_dir: Path) -> Path:
    return Path(pack_dir) / CAPTURE_ACTIVITY_FILENAME


def index_metadata_matches(data: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Match the model/index version while tolerating pre-marker catalogs."""
    return all(
        data.get(key) == value
        for key, value in expected.items()
        if key != INDEX_COMPLETION_MARKER
    )


def load_capture_activity(pack_dir: Path) -> dict[str, Any]:
    """Load the bounded activity log without making startup depend on it."""
    try:
        data = json.loads(_path(pack_dir).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    events = data.get("events")
    if not isinstance(events, list):
        events = []
    return {
        "version": CAPTURE_ACTIVITY_VERSION,
        "events": [event for event in events if isinstance(event, dict)][-MAX_CAPTURE_ACTIVITY_ITEMS:],
    }


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def record_capture_event(
    pack_dir: Path,
    *,
    category: str,
    filename: str,
    digest: str,
    status: str,
    duplicate_of: str = "",
    captured_at: int | None = None,
) -> dict[str, Any]:
    """Append one capture result for the semantic page and return it."""
    data = load_capture_activity(pack_dir)
    event = {
        "id": f"capture-{time.time_ns()}",
        "category": str(category),
        "filename": str(filename),
        "sha256": str(digest),
        "status": str(status),
        "duplicate_of": str(duplicate_of or ""),
        "captured_at": int(captured_at or time.time()),
    }
    data["events"] = [*data["events"], event][-MAX_CAPTURE_ACTIVITY_ITEMS:]
    _write_atomic(_path(pack_dir), data)
    return event


def mark_capture_events_indexed(
    pack_dir: Path,
    *,
    category: str,
    digests: set[str],
    indexed_at: int | None = None,
) -> int:
    """Resolve pending/duplicate activity after a category index completes."""
    if not digests:
        return 0
    data = load_capture_activity(pack_dir)
    changed = 0
    timestamp = int(indexed_at or time.time())
    for event in data["events"]:
        if event.get("category") != category or event.get("sha256") not in digests:
            continue
        if event.get("status") in {"pending", "duplicate"}:
            event["status"] = "indexed" if event.get("status") == "pending" else "deduped"
            event["indexed_at"] = timestamp
            changed += 1
    if changed:
        _write_atomic(_path(pack_dir), data)
    return changed
