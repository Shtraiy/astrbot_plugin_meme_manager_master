"""Lazy semantic capability boundary.

The core plugin can depend on this small adapter without importing FAISS,
embedding providers, or the legacy semantic implementation during startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CapabilityStatus:
    name: str
    available: bool
    reason: str = ""


@dataclass(frozen=True)
class Unavailable:
    reason: str


class LazySemanticCapability:
    def __init__(self, *, loader: Callable[[], Any], enabled: bool = False):
        self._loader = loader
        self._enabled = bool(enabled)
        self._provider: Any | None = None
        self._error: str = ""

    def _load(self) -> Any | None:
        if not self._enabled:
            return None
        if self._provider is not None or self._error:
            return self._provider
        try:
            self._provider = self._loader()
        except Exception as exc:
            self._error = str(exc) or exc.__class__.__name__
        return self._provider

    def status(self) -> CapabilityStatus:
        if not self._enabled:
            return CapabilityStatus("semantic", False, "disabled")
        provider = self._load()
        if provider is None:
            return CapabilityStatus("semantic", False, self._error or "unavailable")
        return CapabilityStatus("semantic", True, "")

    def query(self, request: Any) -> Any:
        provider = self._load()
        if provider is None:
            return Unavailable(self._error or ("disabled" if not self._enabled else "unavailable"))
        query = getattr(provider, "query", None)
        if not callable(query):
            self._error = "provider does not expose query"
            return Unavailable(self._error)
        try:
            return query(request)
        except Exception as exc:
            self._error = str(exc) or exc.__class__.__name__
            return Unavailable(self._error)
