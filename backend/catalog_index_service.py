"""Pack-scoped mutation locks used by ordinary catalog operations."""

from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path
from typing import Any


class CatalogIndexService:
    """Serialize pack mutations and external file operations."""

    def __init__(
        self,
        plugin_data_dir: Path | str,
        *,
        context: Any = None,
        config: dict | None = None,
    ):
        self.plugin_data_dir = Path(plugin_data_dir).resolve()
        self.context = context
        self.config = config or {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._external_pack_operations: dict[str, str] = {}

    def _lock(self, pack_id: str) -> asyncio.Lock:
        return self._locks.setdefault(pack_id, asyncio.Lock())

    @staticmethod
    def _validate_pack_id(pack_id: str) -> str:
        value = str(pack_id or "").strip()
        if not value or not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", value):
            raise ValueError("pack_id 无效")
        return value

    def begin_external_pack_operation(self, pack_id: str, operation: str) -> None:
        pack_id = self._validate_pack_id(pack_id)
        self.assert_pack_mutation_allowed(pack_id, operation)
        self._external_pack_operations[pack_id] = str(operation or "外部文件任务")

    def end_external_pack_operation(self, pack_id: str) -> None:
        self._external_pack_operations.pop(str(pack_id or "").strip(), None)

    def assert_pack_mutation_allowed(
        self, pack_id: str, operation: str = "修改资源包"
    ) -> None:
        pack_id = self._validate_pack_id(pack_id)
        external_operation = self._external_pack_operations.get(pack_id)
        if external_operation:
            raise RuntimeError(
                f"资源包 {pack_id} 正在执行“{external_operation}”，暂时不能{operation}"
            )

    async def run_locked_pack_mutation(
        self, pack_id: str, operation: str, mutation: Any
    ) -> Any:
        pack_id = self._validate_pack_id(pack_id)
        if not callable(mutation):
            raise TypeError("mutation 必须可调用")
        async with self._lock(pack_id):
            self.assert_pack_mutation_allowed(pack_id, operation)
            result = mutation()
            if inspect.isawaitable(result):
                return await result
            return result
