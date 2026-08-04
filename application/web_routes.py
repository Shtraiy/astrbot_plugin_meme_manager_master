"""Framework-neutral route registry used to validate WebUI composition."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WebRouteSpec:
    method: str
    path: str
    handler: str

    def __post_init__(self) -> None:
        method = str(self.method or "").strip().upper()
        path = str(self.path or "").strip()
        handler = str(self.handler or "").strip()
        if not method or not path.startswith("/") or not handler:
            raise ValueError("route spec requires method, absolute path, and handler")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "handler", handler)


class WebRouteRegistry:
    def __init__(self) -> None:
        self._routes: list[WebRouteSpec] = []

    def register(self, spec: WebRouteSpec) -> None:
        if any(route.method == spec.method and route.path == spec.path for route in self._routes):
            raise ValueError(f"duplicate route: {spec.method} {spec.path}")
        self._routes.append(spec)

    def routes(self) -> tuple[WebRouteSpec, ...]:
        return tuple(self._routes)
