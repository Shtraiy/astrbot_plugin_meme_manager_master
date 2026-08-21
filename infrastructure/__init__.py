"""Infrastructure adapters with no framework-facing entry points."""

from .storage_policy import (
    is_safe_category_segment,
    resolve_safe_category_dir,
    safe_extension,
)

__all__ = [
    "is_safe_category_segment",
    "resolve_safe_category_dir",
    "safe_extension",
]
