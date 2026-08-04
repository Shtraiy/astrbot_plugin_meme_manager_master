"""Runtime backup boundary over the legacy pack facade."""

from __future__ import annotations

import importlib
from typing import Any


class PackBackup:
    def __init__(self, backend: Any | None = None):
        self.backend = backend or importlib.import_module(f"{__package__}.pack_storage")

    def export(self, **kwargs: Any):
        return self.backend.export_runtime_backup(**kwargs)

    def import_backup(self, archive_path, **kwargs: Any):
        return self.backend.import_runtime_backup(archive_path, **kwargs)
