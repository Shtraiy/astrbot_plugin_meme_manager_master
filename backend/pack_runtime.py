"""Runtime pack-management boundary over the legacy implementation."""

from __future__ import annotations

import importlib
from typing import Any


class PackRuntime:
    def __init__(self, backend: Any | None = None):
        self.backend = backend or importlib.import_module(f"{__package__}.pack_storage")

    def list(self):
        return self.backend.list_installed_packs()

    def detail(self, pack_id: str):
        return self.backend.get_pack_detail(pack_id)

    def set_default(self, pack_id: str):
        return self.backend.set_default_pack(pack_id)

    def create(self, pack_id: str):
        return self.backend._create_empty_pack(pack_id)
