"""Image repository boundary backed by the legacy MemeStore."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ImageRepository:
    def __init__(self, root: Path | str, *, store: Any | None = None):
        if store is None:
            try:
                from ..storage import MemeStore
            except ImportError:
                from storage import MemeStore

            store = MemeStore(Path(root))
        self.store = store

    def save(
        self,
        content: bytes,
        tags: object = None,
        extension: str = ".png",
        perceptual_threshold: int | None = 6,
    ):
        return self.store._save_image_legacy(content, tags, extension, perceptual_threshold)

    def find_duplicate(self, content: bytes, perceptual_threshold: int | None = 6):
        return self.store.find_duplicate(content, perceptual_threshold)

    def image_paths(self, category: str | None = None) -> list[Path]:
        return self.store.image_paths(category)

    def make_temp_file(self, content: bytes, extension: str = ".png") -> Path:
        return self.store.make_temp_file(content, extension)

    @staticmethod
    def remove_temp_file(path: Path) -> None:
        try:
            from ..storage import MemeStore
        except ImportError:
            from storage import MemeStore

        MemeStore.remove_temp_file(path)
