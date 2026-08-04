"""Filesystem boundary used by pack and catalog adapters."""

from __future__ import annotations

from pathlib import Path


class PathBoundary:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    def child(self, *parts: str) -> Path:
        if not parts:
            raise ValueError("a child path is required")
        candidate = self.root.joinpath(*parts).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes configured root") from exc
        return candidate
