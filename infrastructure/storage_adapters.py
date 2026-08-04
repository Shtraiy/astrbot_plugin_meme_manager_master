"""Adapters that expose the existing MemeStore through stable ports."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

try:
    from ..domain.models import PackContext, SaveResult
    from ..storage import MemeStore
    from .catalog_repository import CatalogRepository
    from .image_repository import ImageRepository
except ImportError:  # standalone test imports from repository root
    from domain.models import PackContext, SaveResult
    from storage import MemeStore
    from infrastructure.catalog_repository import CatalogRepository
    from infrastructure.image_repository import ImageRepository


class MemeStoreCatalogRepository:
    def reconcile(self, pack: PackContext) -> dict[str, Any]:
        repository = CatalogRepository(pack.root)
        changed = int(repository.reconcile())
        return {"pack_id": str(pack.pack_id), "changed": changed > 0, "changed_count": changed}


class MemeStoreImageRepository:
    def __init__(self, root: Path | str):
        self._repository = ImageRepository(Path(root))

    def save(self, content: bytes, tags: Sequence[str] | None = None):
        result = self._repository.save(content, tags=tags)
        return SaveResult(result.status, result.path, result.digest)
