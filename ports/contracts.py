"""Protocol definitions shared by application and adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

try:
    from ..domain.models import CaptureOutcome, PackContext, ReconcileReport, SaveResult, SelectionResult
except ImportError:  # standalone test imports from repository root
    from domain.models import CaptureOutcome, PackContext, ReconcileReport, SaveResult, SelectionResult


@runtime_checkable
class PackResolver(Protocol):
    def resolve(self, pack_id: str) -> PackContext:
        """Resolve a validated pack id into a bounded filesystem context."""


@runtime_checkable
class ImageRepository(Protocol):
    def save(self, content: bytes, tags: Sequence[str] | None = None) -> SaveResult:
        """Persist an image atomically."""


@runtime_checkable
class CatalogRepository(Protocol):
    def reconcile(self, pack: PackContext) -> ReconcileReport:
        """Reconcile catalog metadata for one pack."""


@runtime_checkable
class SelectionService(Protocol):
    def choose(self, request: Mapping[str, Any]) -> SelectionResult:
        """Choose a meme without mutating the inbound event object."""


class CaptureHandler(Protocol):
    def handle(self, request: Any) -> CaptureOutcome:
        """Coordinate capture and return a transport-neutral outcome."""
