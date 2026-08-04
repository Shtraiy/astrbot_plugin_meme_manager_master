"""Small immutable values shared by application and infrastructure layers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")


def _normalized_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text


@dataclass(frozen=True)
class PackId:
    value: str

    def __post_init__(self) -> None:
        value = _normalized_text(self.value, "pack_id")
        if not _SAFE_ID.fullmatch(value) or value in {".", ".."}:
            raise ValueError("invalid pack_id")
        object.__setattr__(self, "value", value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Category:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalized_text(self.value, "category"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class MemeId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalized_text(self.value, "meme_id"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OperationError(Exception):
    code: str
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _normalized_text(self.code, "error code"))
        object.__setattr__(self, "message", _normalized_text(self.message, "error message"))
        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class PackContext:
    pack_id: PackId
    root: Path
    packs_root: Path

    def __post_init__(self) -> None:
        pack_root = Path(self.root).resolve()
        packs_root = Path(self.packs_root).resolve()
        try:
            pack_root.relative_to(packs_root)
        except ValueError as exc:
            raise ValueError("pack root must be inside packs root") from exc
        object.__setattr__(self, "root", pack_root)
        object.__setattr__(self, "packs_root", packs_root)

    def resolve(self, *parts: str) -> Path:
        candidate = self.root.joinpath(*parts).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes pack root") from exc
        return candidate


@dataclass(frozen=True)
class SelectionResult:
    selected_id: MemeId | None = None
    category: Category | None = None
    confidence: float = 0.0
    reason: str = ""

    def __post_init__(self) -> None:
        confidence = max(0.0, min(1.0, float(self.confidence)))
        object.__setattr__(self, "confidence", confidence)
        if self.reason:
            object.__setattr__(self, "reason", str(self.reason).strip())


@dataclass(frozen=True)
class SaveResult:
    """Stable image-write result shared by storage adapters."""

    status: str
    path: Path
    digest: str


class ReconcileReport(TypedDict, total=False):
    pack_id: str
    changed: bool
    changed_count: int
    error: str


class CaptureOutcome(TypedDict, total=False):
    status: str
    saved: bool
    meme_id: str
    error: str
