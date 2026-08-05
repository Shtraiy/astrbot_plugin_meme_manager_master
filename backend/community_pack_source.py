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

    def find_cached(self, pack_id: str):
        return self.backend.find_cached_pack_entry(pack_id)

    def install(self, source: dict[str, Any], **kwargs: Any):
        return self.backend.install_pack_from_github_source(source, **kwargs)

    def install_official_first(self, **kwargs: Any):
        return self.backend.install_first_official_pack_from_index(**kwargs)
