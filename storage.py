"""Storage adapter for the meme_manager_master on-disk data contract."""

from __future__ import annotations

import hashlib
import io
import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from .backend.atomic_io import atomic_write_bytes, atomic_write_json
    from .backend.tagging import CANONICAL_TAGS, canonical_tag, normalize_tags
except ImportError:  # standalone test imports (repo root on sys.path)
    from backend.atomic_io import atomic_write_bytes, atomic_write_json
    from backend.tagging import CANONICAL_TAGS, canonical_tag, normalize_tags

try:
    from PIL import Image
except ImportError:  # Pillow is optional at import time for AstrBot startup.
    Image = None


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
DEFAULT_SEND_REPEAT_WINDOW = 300.0
SEND_COUNT_PENALTY = 0.35
SEND_WEIGHT_MIN = 0.1
SEND_RECOVERY_BASE = 0.35
SEND_RECOVERY_RANGE = 0.65
_IMAGE_FORMAT_EXTENSIONS = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "GIF": ".gif",
    "WEBP": ".webp",
    "BMP": ".bmp",
}


def image_preview_mode(
    *,
    file_size: int,
    mime_type: str,
    requested_size: str,
    raw_preview_limit: int,
    source_limit: int,
) -> str:
    """Choose how the WebUI should represent an image preview."""
    if requested_size == "original":
        return "reject" if file_size > source_limit else "original"
    if file_size > source_limit:
        return "reject"
    if mime_type == "image/gif" and file_size <= raw_preview_limit:
        return "original"
    return "thumbnail"


def detect_image_extension(content: bytes) -> str | None:
    """Validate image bytes and return an extension based on its real format."""
    if Image is None or not content:
        return None
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            return _IMAGE_FORMAT_EXTENSIONS.get(str(image.format or "").upper())
    except Exception:
        return None


DEFAULT_CATEGORY_DESCRIPTIONS = {
    "angry": "当对话包含抱怨、批评或激烈反对时使用",
    "happy": "用于成功确认、积极反馈或庆祝场景",
    "sad": "表达伤心、歉意、遗憾或安慰场景",
    "surprised": "响应超出预期的信息或意外转折",
    "confused": "请求澄清、表达理解障碍或感到困惑",
    "color": "社交场景中的暧昧表达",
    "cpu": "技术讨论中表示思维卡顿",
    "fool": "自嘲或缓和气氛的幽默场景",
    "givemoney": "涉及报酬、奖励或付费讨论时使用",
    "like": "表达对事物或观点的喜爱",
    "see": "表示偷瞄或持续关注",
    "shy": "涉及隐私话题或收到赞美时使用",
    "work": "工作流程、任务分配或进度汇报场景",
    "reply": "等待用户反馈或需要确认时使用",
    "meow": "卖萌或萌系互动场景",
    "baka": "轻微责备或友善吐槽",
    "morning": "早安问候场景",
    "sleep": "涉及作息、熬夜、疲劳或休息场景",
    "sigh": "表达无奈、无语或感慨",
}


@dataclass(frozen=True)
class SaveResult:
    status: str
    path: Path
    digest: str


class MemeStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.memes_dir = self.root / "memes"
        self.tag_index_path = self.memes_dir / "tag_index.json"
        self.metadata_path = self.root / "memes_data.json"
        self.temp_dir = self.root / "temp"
        self._perceptual_hash_cache: dict[Path, tuple[int, int, str | None]] = {}
        # Compose the new storage boundaries while retaining the legacy
        # methods on MemeStore for existing callers.
        try:
            from .infrastructure.catalog_repository import CatalogRepository
            from .infrastructure.image_repository import ImageRepository
            from .infrastructure.selection_state import SelectionState
        except ImportError:
            from infrastructure.catalog_repository import CatalogRepository
            from infrastructure.image_repository import ImageRepository
            from infrastructure.selection_state import SelectionState

        self.catalog_repository = CatalogRepository(self.root, store=self)
        self.image_repository = ImageRepository(self.root, store=self)
        self.selection_state = SelectionState(self.root, store=self)

    @classmethod
    def from_astrbot(cls) -> "MemeStore":
        try:
            # The reference manager resolves the active runtime pack during
            # import.  Use that same directory so captured images, WebUI
            # operations and automatic selection share one filesystem view.
            from .config import ACTIVE_PACK_DIR

            root = Path(ACTIVE_PACK_DIR)
        except Exception:
            try:
                from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

                root = (
                    Path(get_astrbot_plugin_data_path())
                    / "meme_manager_master"
                    / "packs"
                    / "builtin-default"
                )
            except Exception:
                root = (
                    Path(__file__).resolve().parent
                    / "data"
                    / "plugin_data"
                    / "meme_manager_master"
                    / "packs"
                    / "builtin-default"
                )
        return cls(root)

    def available_categories(self) -> set[str]:
        categories = {
            tag
            for item in self.load_catalog().get("items", [])
            if isinstance(item, dict)
            for tag in item.get("tags", [])
            if canonical_tag(tag)
        }
        metadata = self._load_metadata()
        categories.update(
            canonical_tag(category) or category
            for category in metadata
            if canonical_tag(category) or category in CANONICAL_TAGS
        )
        return categories or set(CANONICAL_TAGS)

    def category_descriptions(self) -> dict[str, str]:
        """Return descriptions used by meme_manager_master's category prompt."""
        metadata = self._load_metadata()
        categories = self.available_categories()
        return {
            category: str(
                metadata.get(category)
                or DEFAULT_CATEGORY_DESCRIPTIONS.get(category, "")
            )
            for category in categories
        }

    def save_image(
        self,
        content: bytes,
        tags: object = None,
        extension: str = ".png",
        perceptual_threshold: int | None = 6,
    ) -> SaveResult:
        return self.image_repository.save(content, tags, extension, perceptual_threshold)

    def _save_image_legacy(
        self,
        content: bytes,
        tags: object = None,
        extension: str = ".png",
        perceptual_threshold: int | None = 6,
    ) -> SaveResult:
        if not content:
            raise ValueError("cannot save an empty image")
        normalized_tags = normalize_tags(tags)
        digest = hashlib.sha256(content).hexdigest()
        duplicate = self.find_duplicate(content, perceptual_threshold)
        if duplicate is not None:
            if duplicate.parent != self.memes_dir:
                self.reindex_flat_catalog()
                duplicate = self._find_digest(digest) or duplicate
            self._merge_flat_entry(
                duplicate.name,
                digest=digest,
                tags=normalized_tags,
            )
            return SaveResult("duplicate", duplicate, digest)

        safe_extension = _safe_extension(extension)
        self.memes_dir.mkdir(parents=True, exist_ok=True)
        target = self.memes_dir / self._meme_filename(digest, safe_extension)
        self._atomic_write(target, content)
        self._merge_flat_entry(
            target.name,
            digest=digest,
            tags=normalized_tags,
        )
        return SaveResult("saved", target, digest)

    def find_duplicate(
        self,
        content: bytes,
        perceptual_threshold: int | None = 6,
    ) -> Path | None:
        """Return an exact or perceptually equivalent existing image."""
        if not content:
            return None
        duplicate = self._find_digest(hashlib.sha256(content).hexdigest())
        if duplicate is not None or perceptual_threshold is None:
            return duplicate
        content_hash = _perceptual_hash(content)
        if content_hash is None:
            return None
        return self._find_perceptual_hash(content_hash, perceptual_threshold)

    @staticmethod
    def perceptual_hash(content: bytes) -> str | None:
        """Return an average perceptual hash, or None when Pillow cannot decode it."""
        return _perceptual_hash(content)

    def image_perceptual_hash(self, path: Path) -> str | None:
        """Return a cached perceptual hash for a local image."""
        return self._cached_perceptual_hash(path)

    def is_similar(
        self,
        first: bytes,
        second: bytes,
        perceptual_threshold: int | None = 6,
    ) -> bool:
        """Compare two incoming images before either one is saved."""
        if first == second:
            return True
        if perceptual_threshold is None:
            return False
        first_hash = _perceptual_hash(first)
        second_hash = _perceptual_hash(second)
        return bool(
            first_hash
            and second_hash
            and _hamming_distance(first_hash, second_hash) <= perceptual_threshold
        )

    def pick_image(self, tags: object = None) -> Path | None:
        return self.selection_state.pick(tags)

    def pick_indexed_image(self, preferred_tags: object = None, *, now: float | None = None, repeat_window: float = DEFAULT_SEND_REPEAT_WINDOW) -> Path | None:
        return self.selection_state.pick_indexed(preferred_tags, now=now, repeat_window=repeat_window)

    @staticmethod
    def _send_weight(item: dict, now: float, repeat_window: float) -> float:
        try:
            from .infrastructure.selection_state import SelectionState
        except ImportError:
            from infrastructure.selection_state import SelectionState

        return SelectionState._send_weight(item, now, repeat_window)

    def mark_image_sent(self, path: Path, *, sent_at: float | None = None) -> dict | None:
        return self.selection_state.mark_sent(path, sent_at=sent_at)

    def image_paths(self, category: str | None = None) -> list[Path]:
        """Return flat images; an optional category reads legacy files only."""
        if category is not None:
            if not _is_safe_segment(category):
                return []
            category_dir = self.memes_dir / category
            if not category_dir.is_dir():
                return []
            root = category_dir
        else:
            root = self.memes_dir
        if not root.is_dir():
            return []
        return sorted(
            path for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )

    def directory_categories(self) -> set[str]:
        if not self.memes_dir.is_dir():
            return set()
        return {
            item.name for item in self.memes_dir.iterdir()
            if item.is_dir() and _is_safe_segment(item.name)
        }

    def ensure_catalog_entry(self, *args, digest: str | None = None) -> None:
        """Ensure one flat image is represented in the unified index."""
        if len(args) >= 2 and isinstance(args[0], str):
            legacy_tag, image_path = args[:2]
            if len(args) >= 3 and digest is None:
                digest = args[2]
            if Path(image_path).parent != self.memes_dir:
                self.reindex_flat_catalog()
                return
            tags = [legacy_tag]
        elif args:
            image_path = args[0]
            tags = []
        else:
            return
        image_path = Path(image_path)
        if (
            image_path.parent != self.memes_dir
            or not image_path.is_file()
            or image_path.suffix.lower() not in IMAGE_EXTENSIONS
        ):
            return
        self._merge_flat_entry(
            image_path.name,
            digest=digest or self.image_digest(image_path),
            tags=tags,
        )

    def reconcile_category(self, category: str) -> bool:
        """Repair a legacy directory catalog without making it active again."""
        if not _is_safe_segment(category):
            return False
        category_dir = self.memes_dir / category
        if not category_dir.is_dir():
            return False
        old = self._read_catalog_file(category_dir / "index.json", category=category)
        by_filename = {
            str(item.get("filename")): dict(item)
            for item in old.get("items", [])
            if isinstance(item, dict) and item.get("filename")
        }
        entries = []
        for path in self.image_paths(category):
            entry = by_filename.get(path.name) or self._minimal_catalog_entry(path)
            entry["filename"] = path.name
            entry["tags"] = normalize_tags([category, *(entry.get("tags") or [])])
            entries.append(entry)
        atomic_write_json(
            category_dir / "index.json",
            {"version": 1, "category": category, "items": entries},
        )
        return True

    def reconcile_categories(self, categories) -> int:
        """Reconcile legacy categories once through the flat catalog."""
        safe = {
            str(item) for item in categories if _is_safe_segment(str(item))
        }
        return sum(1 for category in sorted(safe) if self.reconcile_category(category))

    def reconcile_catalogs(self) -> int:
        """Create or repair the unified index for every image on disk."""
        before = {
            str(item.get("filename"))
            for item in self.load_catalog().get("items", [])
            if isinstance(item, dict) and item.get("filename")
        }
        result = self.reindex_flat_catalog()
        after = {
            str(item.get("filename"))
            for item in self.load_catalog().get("items", [])
            if isinstance(item, dict) and item.get("filename")
        }
        return int(
            bool(
                before != after
                or result["processed"] != len(before)
                or result["migrated_file_count"]
                or result["deduplicated_file_count"]
                or result["skipped_path_count"]
            )
        )

    def image_digest(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _minimal_catalog_entry(
        path: Path,
        digest: str | None = None,
        tags: object = None,
    ) -> dict:
        digest = digest or hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "id": f"meme_{digest[:12]}",
            "filename": path.name,
            "sha256": digest,
            "description": "",
            "emotion": "",
            "text": "",
            "tags": normalize_tags(tags),
            "indexed": False,
            "status": "pending",
            "send_count": 0,
            "last_sent_at": 0,
        }

    @staticmethod
    def _normalize_catalog_items(raw_items: object) -> list[dict]:
        if isinstance(raw_items, dict):
            raw_items = [
                dict(value, filename=str(filename))
                if isinstance(value, dict)
                else {"filename": str(filename), "description": str(value or "")}
                for filename, value in raw_items.items()
            ]
        if not isinstance(raw_items, list):
            return []
        result = []
        for raw in raw_items:
            if not isinstance(raw, dict) or not raw.get("filename"):
                continue
            item = dict(raw)
            item["filename"] = Path(str(item["filename"])).name
            item["tags"] = normalize_tags(item.get("tags"))
            result.append(item)
        return result

    def _read_catalog_file(self, path: Path, *, category: str = "") -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {"version": 1, "category": category, "items": []}
        if isinstance(data, list):
            data = {"version": 1, "category": category, "items": data}
        if not isinstance(data, dict):
            return {"version": 1, "category": category, "items": []}
        raw_items = data.get("items")
        if not isinstance(raw_items, (list, dict)):
            for legacy_key in ("images", "entries", "memes", "data"):
                if isinstance(data.get(legacy_key), (list, dict)):
                    raw_items = data[legacy_key]
                    break
        data["items"] = self._normalize_catalog_items(raw_items)
        return data

    def load_catalog(self, category: str | None = None) -> dict:
        """Load the unified catalog; category is a read-only legacy filter."""
        unified = self._read_catalog_file(self.memes_dir / "index.json")
        if category is None or (self.memes_dir / "index.json").is_file():
            if category is not None:
                tag = canonical_tag(category)
                unified["items"] = [
                    item
                    for item in unified["items"]
                    if tag and tag in item.get("tags", [])
                ]
                unified["category"] = category
            unified["version"] = 2
            return unified
        if not _is_safe_segment(category):
            return {"version": 1, "category": category, "items": []}
        return self._read_catalog_file(
            self.memes_dir / category / "index.json", category=category
        )

    def write_catalog(
        self,
        entries_or_category: list[dict] | str,
        entries: list[dict] | dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Write the unified catalog, accepting old category call shapes."""
        legacy_category = (
            entries_or_category if isinstance(entries_or_category, str) else ""
        )
        if legacy_category:
            raw_entries = entries if isinstance(entries, list) else []
            current = self.load_catalog().get("items", [])
            by_filename = {
                str(item.get("filename")): dict(item)
                for item in current
                if isinstance(item, dict) and item.get("filename")
            }
            for raw in raw_entries:
                if not isinstance(raw, dict) or not raw.get("filename"):
                    continue
                item = dict(raw)
                item["tags"] = normalize_tags(
                    [legacy_category, *(item.get("tags") or [])]
                )
                by_filename[str(item["filename"])] = item
            normalized_entries = list(by_filename.values())
            catalog_metadata = metadata or {}
        else:
            normalized_entries = [
                dict(item)
                for item in (entries_or_category if isinstance(entries_or_category, list) else [])
                if isinstance(item, dict) and item.get("filename")
            ]
            normalized_entries = self._normalize_catalog_items(normalized_entries)
            catalog_metadata = entries if isinstance(entries, dict) else (metadata or {})
        self.memes_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 2,
            "updated_at": int(time.time()),
            "items": normalized_entries,
        }
        data.update(catalog_metadata)
        self._atomic_write_json(self.memes_dir / "index.json", data)
        self._atomic_write(
            self.memes_dir / "README.md",
            self._catalog_markdown("表情包", normalized_entries).encode("utf-8"),
        )
        self._write_tag_index(normalized_entries, int(data["updated_at"]))

    def rebuild_tag_index(self) -> dict:
        """Rebuild and return the derived tag lookup from the main catalog."""
        catalog = self.load_catalog()
        return self._write_tag_index(
            catalog.get("items", []),
            int(catalog.get("updated_at") or 0),
        )

    @staticmethod
    def _catalog_item_is_indexed(item: dict) -> bool:
        return bool(item.get("indexed", item.get("status") != "pending"))

    def _build_tag_index(
        self,
        entries: list[dict],
        source_updated_at: int,
    ) -> dict:
        by_tag: dict[str, list[str]] = {}
        lookup_items: dict[str, dict] = {}
        for raw in entries:
            if not isinstance(raw, dict) or not self._catalog_item_is_indexed(raw):
                continue
            filename = Path(str(raw.get("filename", ""))).name
            path = self.memes_dir / filename
            if (
                not filename
                or filename != str(raw.get("filename", ""))
                or not path.is_file()
                or path.suffix.lower() not in IMAGE_EXTENSIONS
            ):
                continue
            raw_tags = raw.get("tags")
            tags = normalize_tags(raw_tags, fallback="") if raw_tags else []
            if tags == ["其他"] and not raw_tags:
                tags = []
            meme_id = str(raw.get("id") or path.stem)
            lookup_items[meme_id] = {
                "filename": filename,
                "tags": tags,
                "indexed": True,
                "send_count": raw.get("send_count", 0),
                "last_sent_at": raw.get("last_sent_at", 0),
            }
            for tag in tags:
                by_tag.setdefault(tag, []).append(meme_id)
        for tag, ids in by_tag.items():
            by_tag[tag] = sorted(set(ids))
        return {
            "version": 1,
            "source_version": 2,
            "source_updated_at": int(source_updated_at),
            "source_mtime_ns": self._catalog_mtime_ns(),
            "updated_at": int(time.time()),
            "by_tag": dict(sorted(by_tag.items())),
            "items": {
                meme_id: lookup_items[meme_id]
                for meme_id in sorted(lookup_items)
            },
        }

    def _write_tag_index(self, entries: object, source_updated_at: int) -> dict:
        normalized_entries = [
            item for item in entries if isinstance(item, dict)
        ] if isinstance(entries, list) else []
        data = self._build_tag_index(normalized_entries, source_updated_at)
        self.memes_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(self.tag_index_path, data)
        return data

    def _load_tag_index(self, catalog: dict | None = None) -> dict:
        expected_source = (
            int(catalog.get("updated_at") or 0) if catalog is not None else None
        )
        try:
            data = json.loads(self.tag_index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            catalog = catalog or self.load_catalog()
            return self._write_tag_index(
                catalog.get("items", []),
                int(catalog.get("updated_at") or 0),
            )
        if not self._valid_tag_index(data, expected_source):
            catalog = catalog or self.load_catalog()
            return self._write_tag_index(
                catalog.get("items", []),
                int(catalog.get("updated_at") or 0),
            )
        return data

    def _valid_tag_index(self, data: object, expected_source: int | None) -> bool:
        if not isinstance(data, dict):
            return False
        if data.get("version") != 1 or data.get("source_version") != 2:
            return False
        if expected_source is not None:
            try:
                if int(data.get("source_updated_at")) != expected_source:
                    return False
            except (TypeError, ValueError):
                return False
        try:
            if int(data.get("source_mtime_ns")) != self._catalog_mtime_ns():
                return False
        except (TypeError, ValueError):
            return False
        by_tag = data.get("by_tag")
        items = data.get("items")
        if not isinstance(by_tag, dict) or not isinstance(items, dict):
            return False
        for tag, ids in by_tag.items():
            if not canonical_tag(tag) or not isinstance(ids, list):
                return False
            if len(ids) != len(set(ids)):
                return False
            for meme_id in ids:
                item = items.get(meme_id)
                if not isinstance(item, dict) or tag not in item.get("tags", []):
                    return False
                filename = Path(str(item.get("filename", ""))).name
                path = self.memes_dir / filename
                if (
                    filename != str(item.get("filename", ""))
                    or not path.is_file()
                    or path.suffix.lower() not in IMAGE_EXTENSIONS
                    or not item.get("indexed", False)
                ):
                    return False
        return True

    def _catalog_mtime_ns(self) -> int:
        try:
            return int((self.memes_dir / "index.json").stat().st_mtime_ns)
        except OSError:
            return 0

    def upsert_catalog_entry(
        self,
        entry_or_category: dict | str,
        entry: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Add or replace one indexed image without discarding other entries."""
        if isinstance(entry_or_category, str):
            category = entry_or_category
            item = dict(entry or {})
            item["tags"] = normalize_tags([category, *(item.get("tags") or [])])
        else:
            item = dict(entry_or_category)
        filename = str(item.get("filename", ""))
        if not filename:
            return
        data = self.load_catalog()
        items = [
            old for old in data.get("items", [])
            if isinstance(old, dict) and old.get("filename") != filename
        ]
        items.append(item)
        self.write_catalog(items, metadata or {})

    def merge_catalog_entry(
        self,
        entry: dict,
        *,
        digest: str,
        tags: object = None,
    ) -> dict:
        """Merge useful metadata into an existing flat image entry."""
        filename = str(entry.get("filename", ""))
        if not filename:
            return {}
        metadata = {
            key: value
            for key, value in entry.items()
            if key not in {"filename", "tags", "id", "sha256"}
        }
        return self._merge_flat_entry(
            filename,
            digest=digest,
            tags=tags if tags is not None else entry.get("tags"),
            metadata=metadata,
        )

    def _merge_flat_entry(
        self,
        filename: str,
        *,
        digest: str,
        tags: object = None,
        metadata: dict | None = None,
    ) -> dict:
        data = self.load_catalog()
        items = [dict(item) for item in data.get("items", []) if isinstance(item, dict)]
        existing = next((item for item in items if item.get("filename") == filename), None)
        if existing is None:
            existing = self._minimal_catalog_entry(
                self.memes_dir / filename, digest=digest, tags=tags
            )
            items.append(existing)
        else:
            existing["sha256"] = digest
            existing["id"] = f"meme_{digest[:12]}"
            existing["tags"] = normalize_tags(
                [*(existing.get("tags") or []), *normalize_tags(tags)]
            )
        if metadata:
            for key, value in metadata.items():
                if value not in (None, "", []) and not existing.get(key):
                    existing[key] = value
        self.write_catalog(items)
        return existing

    def reindex_flat_catalog(self) -> dict[str, int]:
        """Flatten legacy category directories and rebuild one catalog."""
        self.memes_dir.mkdir(parents=True, exist_ok=True)
        direct_paths = self.image_paths()
        legacy_dirs = [
            path
            for path in self.memes_dir.iterdir()
            if path.is_dir() and _is_safe_segment(path.name)
        ]
        source_paths = list(direct_paths)
        for category_dir in legacy_dirs:
            source_paths.extend(self.image_paths(category_dir.name))
        total = len(source_paths)
        unified_catalog = self._read_catalog_file(self.memes_dir / "index.json")
        old_unified = unified_catalog.get("items", [])
        catalog_metadata = {
            key: value
            for key, value in unified_catalog.items()
            if key not in {"version", "updated_at", "items", "category"}
        }
        by_filename = {
            str(item.get("filename")): item
            for item in old_unified
            if isinstance(item, dict) and item.get("filename")
        }
        groups: dict[str, list[tuple[Path, dict]]] = {}
        for source in source_paths:
            digest = self.image_digest(source)
            category = source.parent.name if source.parent != self.memes_dir else ""
            old_entry = by_filename.get(source.name, {})
            if category and category in {item.name for item in legacy_dirs}:
                legacy_catalog = self._read_catalog_file(
                    source.parent / "index.json", category=category
                )
                catalog_metadata.update(
                    {
                        key: value
                        for key, value in legacy_catalog.items()
                        if key not in {"version", "updated_at", "items", "category"}
                    }
                )
                old_entry = next(
                    (
                        item
                        for item in legacy_catalog["items"]
                        if item.get("filename") == source.name
                    ),
                    old_entry,
                )
            entry = dict(old_entry)
            entry.update({"sha256": digest, "filename": source.name})
            entry["tags"] = normalize_tags(
                [category, *(entry.get("tags") or []), entry.get("emotion", "")]
            )
            groups.setdefault(digest, []).append((source, entry))

        reserved: set[str] = set()
        moves: list[tuple[Path, Path]] = []
        final_entries: list[dict] = []
        migrated = 0
        deduplicated = 0
        for digest, records in sorted(groups.items()):
            records.sort(key=lambda record: (record[0].parent != self.memes_dir, str(record[0])))
            source, merged = records[0]
            for duplicate_source, duplicate_entry in records[1:]:
                deduplicated += 1
                merged["tags"] = normalize_tags(
                    [*(merged.get("tags") or []), *(duplicate_entry.get("tags") or [])]
                )
                for key in ("description", "emotion", "text"):
                    if not merged.get(key) and duplicate_entry.get(key):
                        merged[key] = duplicate_entry[key]
                if duplicate_entry.get("send_count", 0) > merged.get("send_count", 0):
                    merged["send_count"] = duplicate_entry["send_count"]
                    merged["last_sent_at"] = duplicate_entry.get("last_sent_at", 0)
                if duplicate_source != source and duplicate_source.exists():
                    duplicate_source.unlink()
            extension = _safe_extension(source.suffix)
            target_name = self._meme_filename(digest, extension, reserved)
            reserved.add(target_name)
            target = self.memes_dir / target_name
            merged.update({"id": target.stem, "filename": target.name, "sha256": digest})
            if source != target:
                temporary = self.memes_dir / f".meme-migrate-{time.time_ns()}-{len(moves)}{extension}"
                source.rename(temporary)
                moves.append((temporary, target))
                migrated += 1
            merged.setdefault("indexed", False)
            merged.setdefault("status", "pending")
            merged.setdefault("send_count", 0)
            merged.setdefault("last_sent_at", 0)
            final_entries.append(merged)

        for temporary, target in moves:
            if target.exists():
                target.unlink()
            temporary.rename(target)
        self.write_catalog(
            sorted(final_entries, key=lambda item: item["filename"]),
            catalog_metadata,
        )

        skipped = 0
        for category_dir in legacy_dirs:
            for managed_name in ("index.json", "README.md"):
                (category_dir / managed_name).unlink(missing_ok=True)
            remaining = list(category_dir.iterdir())
            if remaining:
                skipped += len(remaining)
            else:
                category_dir.rmdir()
        return {
            "processed": total,
            "total": total,
            "migrated_file_count": migrated,
            "deduplicated_file_count": deduplicated,
            "tag_count": len({tag for item in final_entries for tag in item.get("tags", [])}),
            "skipped_path_count": skipped,
        }

    def renumber_category(self, category: str) -> dict[Path, Path]:
        """Rename all category images to stable names such as happy_0001.png."""
        images = self.image_paths(category)
        if not _is_safe_segment(category) or not images:
            return {}
        category_dir = self.memes_dir / category
        mapping = {
            path: category_dir / f"{category}_{index:04d}{path.suffix.lower()}"
            for index, path in enumerate(images, start=1)
        }
        pending: list[tuple[Path, Path, Path]] = []
        for index, (source, target) in enumerate(mapping.items()):
            if source == target:
                continue
            temporary = category_dir / f".meme-renaming-{time.time_ns()}-{index}{source.suffix.lower()}"
            source.rename(temporary)
            pending.append((temporary, source, target))
        for temporary, _source, target in pending:
            temporary.rename(target)
        return mapping

    def reindex_category(self, category: str) -> dict[Path, Path]:
        """Renumber one category and update catalog filename references."""
        images = self.image_paths(category)
        if not _is_safe_segment(category) or not images:
            return {}

        catalog = self.load_catalog(category)
        by_filename = {
            str(item.get("filename")): item
            for item in catalog.get("items", [])
            if isinstance(item, dict) and item.get("filename")
        }
        mapping = self.renumber_category(category)
        entries: list[dict] = []
        for old_path in images:
            new_path = mapping.get(old_path, old_path)
            entry = dict(by_filename.get(old_path.name) or {})
            if not entry:
                entry = self._minimal_catalog_entry(new_path)
            entry["id"] = new_path.stem
            entry["filename"] = new_path.name
            entries.append(entry)

        metadata = {
            key: value
            for key, value in catalog.items()
            if key not in {"version", "category", "updated_at", "items"}
        }
        self.write_catalog(category, entries, metadata)
        return mapping

    def reindex_all_categories(self) -> dict[str, dict[Path, Path]]:
        """Renumber every category without re-running image recognition."""
        return {
            category: mapping
            for category in sorted(self.directory_categories())
            if (mapping := self.reindex_category(category))
        }

    @staticmethod
    def _meme_filename(
        digest: str,
        extension: str,
        reserved: set[str] | None = None,
    ) -> str:
        reserved = reserved or set()
        for length in (12, 16, 20, 24, 32, 64):
            name = f"meme_{digest[:length]}{extension}"
            if name not in reserved:
                return name
        return f"meme_{digest}{extension}"

    def make_temp_file(self, content: bytes, extension: str = ".png") -> Path:
        path = self.temp_dir / f"incoming_{time.time_ns()}{_safe_extension(extension)}"
        self._atomic_write(path, content)
        return path

    @staticmethod
    def remove_temp_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _find_digest(self, digest: str) -> Path | None:
        if not self.memes_dir.is_dir():
            return None
        for candidate in self.memes_dir.rglob("*"):
            if not candidate.is_file() or candidate.name.startswith(".") or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                if hashlib.sha256(candidate.read_bytes()).hexdigest() == digest:
                    return candidate
            except OSError:
                continue
        return None

    def _find_perceptual_hash(self, content_hash: str, threshold: int) -> Path | None:
        threshold = max(0, min(64, int(threshold)))
        for candidate in self.memes_dir.rglob("*") if self.memes_dir.is_dir() else []:
            if (
                not candidate.is_file()
                or candidate.name.startswith(".")
                or candidate.suffix.lower() not in IMAGE_EXTENSIONS
            ):
                continue
            candidate_hash = self._cached_perceptual_hash(candidate)
            if candidate_hash and _hamming_distance(content_hash, candidate_hash) <= threshold:
                return candidate
        return None

    def _cached_perceptual_hash(self, path: Path) -> str | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        cache_key = (stat.st_mtime_ns, stat.st_size)
        cached = self._perceptual_hash_cache.get(path)
        if cached and cached[:2] == cache_key:
            return cached[2]
        try:
            value = _perceptual_hash(path.read_bytes())
        except OSError:
            value = None
        self._perceptual_hash_cache[path] = (*cache_key, value)
        return value

    def _load_metadata(self) -> dict[str, str]:
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _ensure_category_description(self, category: str) -> None:
        metadata = self._load_metadata()
        if category in metadata:
            return
        metadata[category] = DEFAULT_CATEGORY_DESCRIPTIONS.get(
            category, "自动收集的表情包分类，请补充描述"
        )
        self._atomic_write_json(self.metadata_path, metadata)

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        atomic_write_bytes(path, content)

    def _next_filename(self, category: str, extension: str, digest: str) -> str:
        pattern = re.compile(rf"^{re.escape(category)}_(\d+)$", re.IGNORECASE)
        numbers = [
            int(match.group(1))
            for path in self.image_paths(category)
            if (match := pattern.match(path.stem))
        ]
        if numbers or (self.memes_dir / category / "index.json").exists():
            return f"{category}_{max(numbers, default=0) + 1:04d}{extension}"
        return f"stolen_{time.time_ns()}_{digest[:12]}{extension}"

    @staticmethod
    def _catalog_markdown(category: str, entries: list[dict]) -> str:
        lines = [
            f"# {category} 表情包索引",
            "",
            "此文件由 astrbot_plugin_meme_manager_master 自动生成，请勿手动修改 index.json。",
            "",
            "| 编号 | 文件 | 情绪 | 描述 | 标签 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for entry in entries:
            tags = ", ".join(str(item) for item in entry.get("tags", []) if item)
            values = [
                entry.get("id", ""),
                entry.get("filename", ""),
                entry.get("emotion", ""),
                entry.get("description", ""),
                tags,
            ]
            escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
            lines.append("| " + " | ".join(escaped) + " |")
        return "\n".join(lines) + "\n"

    @classmethod
    def _atomic_write_json(cls, path: Path, data: dict) -> None:
        atomic_write_json(path, data)


def is_safe_category_segment(value: str) -> bool:
    """Validate one on-disk category segment, including Unicode names."""
    normalized = str(value or "")
    if (
        not normalized
        or normalized != normalized.strip()
        or normalized in {".", ".."}
        or "/" in normalized
        or "\\" in normalized
        or any(ord(char) < 32 for char in normalized)
        or any(char in normalized for char in '<>:"|?*')
    ):
        return False
    return Path(normalized).name == normalized


def resolve_safe_category_dir(root: Path | str, category: str) -> Path:
    """Resolve one category directory without allowing it to escape ``root``."""
    normalized = str(category or "").strip()
    if not is_safe_category_segment(normalized):
        raise ValueError("分类名非法")

    root_path = Path(root).expanduser().resolve(strict=False)
    target_path = (root_path / normalized).resolve(strict=False)
    try:
        target_path.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("分类目录超出表情包目录范围") from exc
    return target_path


def scan_pack_emojis(memes_dir: Path | str) -> dict[str, list[str]]:
    """Scan one pack into virtual tag buckets backed by the flat catalog."""
    root = Path(memes_dir)
    if not root.is_dir():
        return {}
    store = MemeStore(root.parent)
    store.reindex_flat_catalog()
    result: dict[str, list[str]] = {}
    for item in store.load_catalog().get("items", []):
        if not isinstance(item, dict):
            continue
        filename = Path(str(item.get("filename") or "")).name
        path = root / filename
        if filename != str(item.get("filename")) or not path.is_file():
            continue
        for tag in item.get("tags", []):
            result.setdefault(str(tag), []).append(filename)
    return {
        tag: sorted(set(names), key=str.casefold)
        for tag, names in sorted(result.items(), key=lambda pair: pair[0])
    }


def _is_safe_segment(value: str) -> bool:
    return is_safe_category_segment(value)


def _safe_extension(extension: str) -> str:
    extension = str(extension or ".png").lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    return extension if extension in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"} else ".png"


def _perceptual_hash(content: bytes) -> str | None:
    """Build a small average hash that survives common resize/compression changes."""
    if Image is None or not content:
        return None
    try:
        with Image.open(io.BytesIO(content)) as image:
            try:
                image.seek(0)
            except EOFError:
                pass
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            pixels = list(image.convert("L").resize((8, 7), resampling).getdata())
    except Exception:
        return None
    if not pixels:
        return None
    average = sum(pixels) / len(pixels)
    bits = sum((1 << index) for index, pixel in enumerate(pixels) if pixel >= average)
    # Keep the signature at 64 bits while retaining brightness information.
    # A plain average hash would make every solid-color image identical.
    return f"{int(round(average)) & 0xff:02x}{bits:014x}"


def _hamming_distance(first: str, second: str) -> int:
    try:
        xor = int(first, 16) ^ int(second, 16)
    except (TypeError, ValueError):
        return 64
    return bin(xor).count("1")


# Compatibility exports now delegate policy decisions to the infrastructure
# boundary.  They intentionally remain defined here for legacy imports.
def is_safe_category_segment(value: str) -> bool:
    try:
        from .infrastructure.storage_policy import is_safe_category_segment as policy
    except ImportError:
        from infrastructure.storage_policy import is_safe_category_segment as policy

    return policy(value)


def resolve_safe_category_dir(root: Path | str, category: str) -> Path:
    try:
        from .infrastructure.storage_policy import resolve_safe_category_dir as policy
    except ImportError:
        from infrastructure.storage_policy import resolve_safe_category_dir as policy

    return policy(root, category)


def _safe_extension(extension: str) -> str:
    try:
        from .infrastructure.storage_policy import safe_extension
    except ImportError:
        from infrastructure.storage_policy import safe_extension

    return safe_extension(extension)
