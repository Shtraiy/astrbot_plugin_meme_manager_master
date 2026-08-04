"""Community pack source boundary over the legacy pack facade."""

from __future__ import annotations

import importlib
from typing import Any


class CommunityPackSource:
    def __init__(self, backend: Any | None = None):
        self.backend = backend or importlib.import_module(f"{__package__}.pack_storage")

    def fetch(self, **kwargs: Any):
        return self.backend.fetch_and_cache_community_index(**kwargs)

    def cached(self):
        return self.backend.load_cached_community_index()

    def install(self, source: str, **kwargs: Any):
        return self.backend.install_pack_from_github_source(source, **kwargs)
