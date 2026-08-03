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
except ImportError:  # standalone test imports (repo root on sys.path)
    from backend.atomic_io import atomic_write_bytes, atomic_write_json

try:
    from PIL import Image
except ImportError:  # Pillow is optional at import time for AstrBot startup.
    Image = None


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
DEFAULT_SEND_REPEAT_WINDOW = 300.0
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
        self.metadata_path = self.root / "memes_data.json"
        self.temp_dir = self.root / "temp"
        self._perceptual_hash_cache: dict[Path, tuple[int, int, str | None]] = {}

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
        categories = set()
        if self.memes_dir.is_dir():
            categories = {
                item.name for item in self.memes_dir.iterdir() if item.is_dir()
            }
        metadata = self._load_metadata()
        categories.update(metadata)
        return categories or set(DEFAULT_CATEGORY_DESCRIPTIONS)

    def category_descriptions(self) -> dict[str, str]:
        """Return descriptions used by meme_manager_master's category prompt."""
        metadata = self._load_metadata()
        categories = self.available_categories()
        return {
            category: str(metadata.get(category) or DEFAULT_CATEGORY_DESCRIPTIONS.get(category, ""))
            for category in categories
        }

    def save_image(
        self,
        content: bytes,
        category: str,
        extension: str = ".png",
        perceptual_threshold: int | None = 6,
    ) -> SaveResult:
        if not content:
            raise ValueError("cannot save an empty image")
        if not _is_safe_segment(category):
            raise ValueError(f"unsafe category: {category!r}")
        digest = hashlib.sha256(content).hexdigest()
        duplicate = self.find_duplicate(content, perceptual_threshold)
        if duplicate is not None:
            # A copied/legacy category may contain the image but no catalog
            # yet.  Keep the duplicate result fast while repairing that
            # category's two index files on the same code path.
            duplicate_category = self._category_for_path(duplicate)
            if duplicate_category:
                self.ensure_catalog_entry(duplicate_category, duplicate, digest)
            return SaveResult("duplicate", duplicate, digest)

        safe_extension = _safe_extension(extension)
        target_dir = self.memes_dir / category
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / self._next_filename(category, safe_extension, digest)
        self._atomic_write(target, content)
        self._ensure_category_description(category)
        self.ensure_catalog_entry(category, target, digest)
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

    def pick_image(self, category: str) -> Path | None:
        """Pick one image from a safe meme_manager_master category directory."""
        if not _is_safe_segment(category):
            return None
        category_dir = self.memes_dir / category
        if not category_dir.is_dir():
            return None
        candidates = [
            path
            for path in category_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
        return random.choice(candidates) if candidates else None

    def pick_indexed_image(
        self,
        category: str,
        *,
        now: float | None = None,
        repeat_window: float = DEFAULT_SEND_REPEAT_WINDOW,
    ) -> Path | None:
        """Pick an indexed image, reducing the weight of recently sent ones."""
        if not _is_safe_segment(category):
            return None
        category_dir = self.memes_dir / category
        if not category_dir.is_dir():
            return None
        current_time = time.time() if now is None else float(now)
        candidates: list[Path] = []
        weights: list[float] = []
        for item in self.load_catalog(category).get("items", []):
            if not isinstance(item, dict):
                continue
            filename = Path(str(item.get("filename", ""))).name
            path = category_dir / filename
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
        """Return a decaying selection weight for one catalog entry."""
        if repeat_window <= 0:
            return 1.0
        try:
            last_sent_at = float(item.get("last_sent_at") or 0.0)
        except (TypeError, ValueError):
            last_sent_at = 0.0
        if last_sent_at <= 0:
            return 1.0
        age = max(0.0, now - last_sent_at)
        recency = max(0.0, min(1.0, 1.0 - age / repeat_window))
        try:
            send_count = max(0, int(item.get("send_count") or 0))
        except (TypeError, ValueError):
            send_count = 0
        penalty = min(0.9, 0.45 + 0.1 * min(send_count, 4))
        return max(0.1, 1.0 - recency * penalty)

    def mark_image_sent(
        self,
        path: Path,
        *,
        sent_at: float | None = None,
    ) -> dict | None:
        """Persist one successful send marker on the image catalog entry."""
        image_path = Path(path)
        category = self._category_for_path(image_path)
        if category is None or not image_path.is_file():
            return None
        data = self.load_catalog(category)
        items = [item for item in data.get("items", []) if isinstance(item, dict)]
        entry = next(
            (item for item in items if item.get("filename") == image_path.name),
            None,
        )
        if entry is None:
            self.ensure_catalog_entry(category, image_path)
            data = self.load_catalog(category)
            items = [item for item in data.get("items", []) if isinstance(item, dict)]
            entry = next(
                (item for item in items if item.get("filename") == image_path.name),
                None,
            )
        if entry is None:
            return None
        try:
            send_count = max(0, int(entry.get("send_count") or 0))
        except (TypeError, ValueError):
            send_count = 0
        entry["send_count"] = send_count + 1
        entry["last_sent_at"] = float(time.time() if sent_at is None else sent_at)
        metadata = {
            key: value
            for key, value in data.items()
            if key not in {"version", "category", "updated_at", "items"}
        }
        self.write_catalog(category, items, metadata)
        return dict(entry)

    def image_paths(self, category: str) -> list[Path]:
        """Return image files in one safe category, excluding catalog documents."""
        if not _is_safe_segment(category):
            return []
        category_dir = self.memes_dir / category
        if not category_dir.is_dir():
            return []
        return sorted(
            path for path in category_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )

    def directory_categories(self) -> set[str]:
        if not self.memes_dir.is_dir():
            return set()
        return {
            item.name for item in self.memes_dir.iterdir()
            if item.is_dir() and _is_safe_segment(item.name)
        }

    def ensure_catalog_entry(
        self,
        category: str,
        path: Path,
        digest: str | None = None,
    ) -> None:
        """Ensure one image is represented in both category index files."""
        if not _is_safe_segment(category):
            return
        image_path = Path(path)
        category_dir = self.memes_dir / category
        try:
            relative = image_path.resolve().relative_to(category_dir.resolve())
        except ValueError:
            return
        if (
            len(relative.parts) != 1
            or not image_path.is_file()
            or image_path.suffix.lower() not in IMAGE_EXTENSIONS
        ):
            return

        data = self.load_catalog(category)
        filename = image_path.name
        existing_items = [
            item for item in data.get("items", []) if isinstance(item, dict)
        ]
        if any(
            isinstance(item, dict) and item.get("filename") == filename
            for item in existing_items
        ):
            # Existing rich metadata must never be replaced by a placeholder.
            if (category_dir / "index.json").is_file() and (category_dir / "README.md").is_file():
                return
            metadata = {
                key: value
                for key, value in data.items()
                if key not in {"version", "category", "updated_at", "items"}
            }
            self.write_catalog(category, existing_items, metadata)
            return

        entry = self._minimal_catalog_entry(
            image_path,
            digest=digest,
        )
        self.upsert_catalog_entry(category, entry)

    def reconcile_category(self, category: str) -> bool:
        """Repair one category and return whether files were rewritten."""
        if not _is_safe_segment(category):
            return False
        category_dir = self.memes_dir / category
        if not category_dir.is_dir():
            return False
        data = self.load_catalog(category)
        entries = [
            item for item in data.get("items", []) if isinstance(item, dict)
        ]
        known = {
            str(item.get("filename"))
            for item in entries
            if item.get("filename")
        }
        changed = False
        image_names = {path.name for path in self.image_paths(category)}
        filtered_entries = [
            item
            for item in entries
            if str(item.get("filename") or "") in image_names
        ]
        if len(filtered_entries) != len(entries):
            entries = filtered_entries
            known = {
                str(item.get("filename"))
                for item in entries
                if item.get("filename")
            }
            changed = True
        for image_path in self.image_paths(category):
            if image_path.name in known:
                continue
            entries.append(self._minimal_catalog_entry(image_path))
            known.add(image_path.name)
            changed = True

        index_path = category_dir / "index.json"
        readme_path = category_dir / "README.md"
        if changed or not index_path.is_file() or not readme_path.is_file():
            metadata = {
                key: value
                for key, value in data.items()
                if key not in {"version", "category", "updated_at", "items"}
            }
            self.write_catalog(category, entries, metadata)
            return True
        return False

    def reconcile_categories(self, categories) -> int:
        """Repair only the given categories; returns the number rewritten."""
        safe = sorted(
            {str(item) for item in categories if _is_safe_segment(str(item))}
        )
        return sum(1 for category in safe if self.reconcile_category(category))

    def reconcile_catalogs(self) -> int:
        """Create or repair indexes for every image already on disk."""
        return self.reconcile_categories(self.directory_categories())

    def image_digest(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _category_for_path(self, path: Path) -> str | None:
        try:
            relative = Path(path).resolve().relative_to(self.memes_dir.resolve())
        except ValueError:
            return None
        if len(relative.parts) != 2:
            return None
        category = relative.parts[0]
        return category if _is_safe_segment(category) else None

    @staticmethod
    def _minimal_catalog_entry(path: Path, digest: str | None = None) -> dict:
        return {
            "filename": path.name,
            "sha256": digest or hashlib.sha256(path.read_bytes()).hexdigest(),
            "description": "",
            "emotion": "",
            "text": "",
            "tags": [],
            "status": "pending",
        }

    def load_catalog(self, category: str) -> dict:
        if not _is_safe_segment(category):
            return {"version": 1, "category": category, "items": []}
        path = self.memes_dir / category / "index.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {"version": 1, "category": category, "items": []}
        if isinstance(data, list):
            data = {"version": 1, "category": category, "items": data}
        if not isinstance(data, dict):
            return {"version": 1, "category": category, "items": []}
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            for legacy_key in ("images", "entries", "memes", "data"):
                candidate = data.get(legacy_key)
                if isinstance(candidate, (list, dict)):
                    raw_items = candidate
                    break
        if isinstance(raw_items, dict):
            normalized_items = []
            for filename, value in raw_items.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("filename", str(filename))
                else:
                    item = {"filename": str(filename), "description": str(value or "")}
                normalized_items.append(item)
            raw_items = normalized_items
        if not isinstance(raw_items, list):
            raw_items = []
        data["category"] = str(data.get("category") or category)
        data["items"] = [item for item in raw_items if isinstance(item, dict)]
        return data

    def write_catalog(
        self,
        category: str,
        entries: list[dict],
        metadata: dict | None = None,
    ) -> None:
        if not _is_safe_segment(category):
            raise ValueError(f"unsafe category: {category!r}")
        category_dir = self.memes_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "category": category,
            "updated_at": int(time.time()),
            "items": entries,
        }
        if isinstance(metadata, dict):
            data.update(metadata)
        self._atomic_write_json(category_dir / "index.json", data)
        self._atomic_write(
            category_dir / "README.md",
            self._catalog_markdown(category, entries).encode("utf-8"),
        )

    def upsert_catalog_entry(
        self,
        category: str,
        entry: dict,
        metadata: dict | None = None,
    ) -> None:
        """Add or replace one indexed image without discarding other entries."""
        filename = str(entry.get("filename", ""))
        if not filename:
            return
        data = self.load_catalog(category)
        items = [
            item for item in data.get("items", [])
            if isinstance(item, dict) and item.get("filename") != filename
        ]
        items.append(entry)
        catalog_metadata = {
            key: value
            for key, value in data.items()
            if key not in {"version", "category", "updated_at", "items"}
        }
        if isinstance(metadata, dict):
            catalog_metadata.update(metadata)
        self.write_catalog(category, items, catalog_metadata)

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
    """Scan one pack using the same image contract as runtime selection."""
    root = Path(memes_dir)
    if not root.is_dir():
        return {}

    result: dict[str, list[str]] = {}
    for category_dir in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if not category_dir.is_dir() or not is_safe_category_segment(category_dir.name):
            continue
        result[category_dir.name] = [
            path.name
            for path in sorted(
                category_dir.iterdir(), key=lambda item: item.name.casefold()
            )
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
    return result


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
