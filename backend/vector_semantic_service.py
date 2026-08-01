"""Optional vector-semantic facade: embeddings, FAISS, rebuild and search.

This service is only created when ``vector_semantic_enabled`` is configured and
FAISS is importable.  Every method returns an explicit capability error when
the vector manager is unavailable, instead of failing with a vague 500.
"""

from __future__ import annotations

from typing import Any


VECTOR_CAPABILITY_ERROR = (
    "向量语义能力未启用：请启用 vector_semantic_enabled 配置并安装 faiss-cpu。"
)


class VectorSemanticService:
    def __init__(self, manager: Any = None):
        self._manager = manager

    @property
    def manager(self) -> Any:
        return self._manager

    @property
    def enabled(self) -> bool:
        return self._manager is not None

    def _require(self) -> Any:
        if self._manager is None:
            raise RuntimeError(VECTOR_CAPABILITY_ERROR)
        return self._manager

    def status(self, pack_id: str) -> dict[str, Any]:
        return self._require().status(pack_id)

    def resolve_embedding_provider(self, pack_id: str = "") -> Any:
        return self._require()._resolve_embedding_provider(pack_id)

    async def save_image_manual_semantic(
        self, pack_id: str, image_path, **kwargs
    ) -> dict[str, Any]:
        return await self._require().save_image_manual_semantic(
            pack_id, image_path, **kwargs
        )

    async def start(self, pack_id: str, **kwargs) -> dict[str, Any]:
        return await self._require().start(pack_id, **kwargs)

    async def pause(self, pack_id: str) -> dict[str, Any]:
        return await self._require().pause(pack_id)

    async def resume(self, pack_id: str, **kwargs) -> dict[str, Any]:
        return await self._require().resume(pack_id, **kwargs)

    async def retry(self, pack_id: str) -> dict[str, Any]:
        return await self._require().retry(pack_id)

    async def rebuild_index(self, pack_id: str, **kwargs) -> dict[str, Any]:
        return await self._require().rebuild_index(pack_id, **kwargs)

    async def clear_local_semantic_state(self, pack_id: str) -> dict[str, Any]:
        return await self._require().clear_local_semantic_state(pack_id)

    async def delete_all_semantic_data(self, pack_id: str) -> dict[str, Any]:
        return await self._require().delete_all_semantic_data(pack_id)
