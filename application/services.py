"""Small orchestration services used by adapters and compatibility facades.

PackRuntime/PackTransfer/CommunityPack 服务是过渡 seam:在 backend 迁移到
ports 契约之前暂时直接依赖 legacy 实现;迁移完成后应收敛为面向 ports 的实现。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

try:
    from ..domain.models import CaptureOutcome, Category, MemeId, PackContext, ReconcileReport, SelectionResult
except ImportError:  # standalone test imports from repository root
    from domain.models import CaptureOutcome, Category, MemeId, PackContext, ReconcileReport, SelectionResult


class PackService:
    def __init__(self, resolver: Any):
        self._resolver = resolver

    def resolve(self, pack_id: str) -> PackContext:
        return self._resolver.resolve(pack_id)


class PackTransferService:
    """Stable facade over the legacy archive/pack transfer implementation."""

    def __init__(self, legacy_storage: Any):
        try:
            from ..backend.pack_transfer import PackTransfer
        except ImportError:
            from backend.pack_transfer import PackTransfer

        self._legacy = PackTransfer(legacy_storage)

    def inspect(self, archive_path: Any, suggested_pack_id: str | None = None) -> Any:
        return self._legacy.inspect(archive_path, suggested_pack_id)

    def export(self, pack_id: str, **kwargs: Any) -> Any:
        return self._legacy.export(pack_id, **kwargs)

    def import_pack(self, archive_path: Any, **kwargs: Any) -> Any:
        return self._legacy.import_pack(archive_path, **kwargs)

    def uninstall(self, pack_id: str, **kwargs: Any) -> Any:
        return self._legacy.uninstall(pack_id, **kwargs)


class PackRuntimeService:
    """Application facade for pack listing, detail and default switching."""

    def __init__(self, legacy_storage: Any):
        try:
            from ..backend.pack_runtime import PackRuntime
        except ImportError:
            from backend.pack_runtime import PackRuntime

        self._runtime = PackRuntime(legacy_storage)

    def list(self):
        return self._runtime.list()

    def detail(self, pack_id: str):
        return self._runtime.detail(pack_id)

    def set_default(self, pack_id: str):
        return self._runtime.set_default(pack_id)


class CommunityPackService:
    def __init__(self, legacy_storage: Any):
        try:
            from ..backend.community_pack_source import CommunityPackSource
        except ImportError:
            from backend.community_pack_source import CommunityPackSource

        self._source = CommunityPackSource(legacy_storage)

    def fetch(self, **kwargs: Any):
        return self._source.fetch(**kwargs)

    def cached(self):
        return self._source.cached()

    def find_cached(self, pack_id: str):
        return self._source.find_cached(pack_id)

    def install(self, source: dict[str, Any], **kwargs: Any):
        return self._source.install(source, **kwargs)

    def install_official_first(self, **kwargs: Any):
        return self._source.install_official_first(**kwargs)


class CatalogService:
    def __init__(self, repository: Any):
        self._repository = repository

    def reconcile(self, pack: PackContext) -> ReconcileReport:
        return self._repository.reconcile(pack)


class SelectionApplicationService:
    def __init__(self, chooser: Callable[[Mapping[str, Any]], Any]):
        self._chooser = chooser

    def choose(self, request: Mapping[str, Any]) -> SelectionResult:
        raw = self._chooser(request)
        if isinstance(raw, SelectionResult):
            return raw
        if not isinstance(raw, Mapping):
            return SelectionResult(reason="selection unavailable")
        try:
            selected = raw.get("selected_id")
            category = raw.get("category")
            return SelectionResult(
                selected_id=MemeId(selected) if selected else None,
                category=Category(category) if category else None,
                confidence=raw.get("confidence", 0.0),
                reason=str(raw.get("reason") or "").strip(),
            )
        except (TypeError, ValueError):
            return SelectionResult(reason="invalid selection result")


class CaptureService:
    def __init__(self, processor: Callable[[Any], Any]):
        self._processor = processor

    def handle(self, request: Any) -> CaptureOutcome:
        return self._processor(request)
