"""Pure path and file-policy helpers shared by storage adapters."""

from __future__ import annotations

from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def is_safe_category_segment(value: str) -> bool:
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
    normalized = str(category or "").strip()
    if not is_safe_category_segment(normalized):
        raise ValueError("invalid category name")
    root_path = Path(root).expanduser().resolve(strict=False)
    target = (root_path / normalized).resolve(strict=False)
    try:
        target.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("category path escapes root") from exc
    return target


def safe_extension(extension: str | None) -> str:
    value = str(extension or ".png").lower()
    if not value.startswith("."):
        value = f".{value}"
    if value == ".jpeg":
        return ".jpg"
    return value if value in IMAGE_EXTENSIONS else ".png"
