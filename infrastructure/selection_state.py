"""Selection and send-receipt boundary backed by MemeStore."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

try:
    from ..backend.tagging import normalize_tags
    from .storage_policy import IMAGE_EXTENSIONS
except ImportError:
    from backend.tagging import normalize_tags
    from infrastructure.storage_policy import IMAGE_EXTENSIONS


class SelectionState:
    def __init__(self, root: Path | str, *, store: Any | None = None):
        if store is None:
            try:
                from ..storage import MemeStore
            except ImportError:
                from storage import MemeStore

            store = MemeStore(Path(root))
        self.store = store

    def pick(self, tags: object = None):
        preferred = set(normalize_tags(tags, fallback="")) if tags else set()
        candidates = [
            path
            for item in self.store.load_catalog().get("items", [])
            if isinstance(item, dict)
            and (not preferred or preferred.intersection(item.get("tags", [])))
            and (path := self.store.memes_dir / Path(str(item.get("filename", ""))).name).is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
        return random.choice(candidates) if candidates else None

    def pick_indexed(
        self,
        preferred_tags: object = None,
        *,
        now: float | None = None,
        repeat_window: float = 300.0,
    ):
        tags = set(normalize_tags(preferred_tags, fallback="")) if preferred_tags else set()
        current_time = time.time() if now is None else float(now)
        lookup = self.store._load_tag_index()
        lookup_items = lookup.get("items", {})
        candidate_ids: set[str] = set()
        if tags:
            for tag in tags:
                candidate_ids.update(lookup.get("by_tag", {}).get(tag, []))
        else:
            candidate_ids.update(lookup_items)
        candidates: list[Path] = []
        weights: list[float] = []
        for meme_id in sorted(candidate_ids):
            item = lookup_items.get(meme_id)
            if not isinstance(item, dict):
                continue
            filename = Path(str(item.get("filename", ""))).name
            path = self.store.memes_dir / filename
            if (
                filename == str(item.get("filename", ""))
                and path.is_file()
                and path.suffix.lower() in IMAGE_EXTENSIONS
            ):
                candidates.append(path)
                weights.append(self._send_weight(item, current_time, repeat_window))
        if not candidates:
            return None
        return random.choices(candidates, weights=weights, k=1)[0]

    @staticmethod
    def _send_weight(item: dict, now: float, repeat_window: float) -> float:
        if repeat_window <= 0:
            return 1.0
        try:
            last_sent_at = float(item.get("last_sent_at") or 0.0)
        except (TypeError, ValueError):
            last_sent_at = 0.0
        if last_sent_at <= 0:
            return 1.0
        try:
            send_count = max(0, int(item.get("send_count") or 0))
        except (TypeError, ValueError):
            send_count = 0
        age = max(0.0, now - last_sent_at)
        recovery = min(age / repeat_window, 1.0)
        count_factor = 1.0 / (1.0 + 0.35 * send_count)
        recovery_factor = 0.35 + 0.65 * recovery
        return max(0.1, count_factor * recovery_factor)

    def mark_sent(self, path: Path, *, sent_at: float | None = None):
        image_path = Path(path)
        try:
            image_path.resolve().relative_to(self.store.memes_dir.resolve())
        except ValueError:
            return None
        if image_path.parent != self.store.memes_dir or not image_path.is_file():
            return None
        data = self.store.load_catalog()
        items = [item for item in data.get("items", []) if isinstance(item, dict)]
        entry = next((item for item in items if item.get("filename") == image_path.name), None)
        if entry is None:
            self.store.ensure_catalog_entry(image_path)
            data = self.store.load_catalog()
            items = [item for item in data.get("items", []) if isinstance(item, dict)]
            entry = next((item for item in items if item.get("filename") == image_path.name), None)
        if entry is None:
            return None
        try:
            send_count = max(0, int(entry.get("send_count") or 0))
        except (TypeError, ValueError):
            send_count = 0
        entry["send_count"] = send_count + 1
        entry["last_sent_at"] = float(time.time() if sent_at is None else sent_at)
        metadata = {
            key: value for key, value in data.items()
            if key not in {"version", "updated_at", "items"}
        }
        self.store.write_catalog(items, metadata)
        return dict(entry)
