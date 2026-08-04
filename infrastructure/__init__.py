"""Infrastructure adapters with no framework-facing entry points."""

from .catalog_repository import CatalogLock, CatalogRepository
from .image_repository import ImageRepository
from .selection_state import SelectionState
from .storage_policy import (
    is_safe_category_segment,
    resolve_safe_category_dir,
    safe_extension,
)

__all__ = [
    "CatalogLock",
    "CatalogRepository",
    "ImageRepository",
    "SelectionState",
    "is_safe_category_segment",
    "resolve_safe_category_dir",
    "safe_extension",
]
