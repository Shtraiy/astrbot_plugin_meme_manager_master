"""Archive transfer boundary over the legacy pack facade."""

from __future__ import annotations

import importlib
from typing import Any


class PackTransfer:
    def __init__(self, backend: Any | None = None):
        self.backend = backend or importlib.import_module(f"{__package__}.pack_storage")

    def inspect(self, archive_path, suggested_pack_id: str | None = None):
        return self.backend.inspect_pack_archive(archive_path, suggested_pack_id)

    def export(self, pack_id: str, **kwargs: Any):
        return self.backend.export_pack_archive(pack_id, **kwargs)

    def import_pack(self, archive_path, **kwargs: Any):
        return self.backend.import_pack_archive(archive_path, **kwargs)

    def uninstall(self, pack_id: str, **kwargs: Any):
        return self.backend.uninstall_pack(pack_id, **kwargs)
