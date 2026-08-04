"""Fail-closed security checks for state-changing plugin Web APIs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class WebSecurityDecision:
    """Result of validating the host-provided WebUI security context."""

    allowed: bool
    status: int = 200
    code: str = ""
    message: str = ""


def _header(headers, name: str) -> str:
    if not headers:
        return ""
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value:
            return str(value).strip()
    lowered_name = name.lower()
    if isinstance(headers, dict):
        for key, value in headers.items():
            if str(key).lower() == lowered_name and value:
                return str(value).strip()
    return ""


def _request_proxies(request_obj):
    yield request_obj
    try:
        from astrbot.api.web import request as host_request
    except (ImportError, AttributeError):
        return
    if host_request is not request_obj:
        yield host_request


def _username(request_obj) -> str:
    for proxy in _request_proxies(request_obj):
        value = getattr(proxy, "username", None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _host(request_obj, headers) -> str:
    host = _header(headers, "Host")
    if host:
        return host
    for proxy in _request_proxies(request_obj):
        value = getattr(proxy, "host", None)
        if value:
            return str(value).strip()
        url = getattr(proxy, "url", None)
        value = getattr(url, "netloc", None)
        if value:
            return str(value).strip()
    return ""


def _origin_matches_host(candidate: str, host: str) -> bool:
    if not candidate or not host or candidate.lower() == "null":
        return False
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.netloc.casefold() == host.casefold()
    )


def check_web_mutation_access(request_obj) -> WebSecurityDecision:
    """Require host authentication and same-origin evidence for mutations."""
    if not _username(request_obj):
        return WebSecurityDecision(
            allowed=False,
            status=401,
            code="web_security_context_missing",
            message="缺少 WebUI 身份认证上下文，已拒绝写操作",
        )

    headers = None
    for proxy in _request_proxies(request_obj):
        candidate = getattr(proxy, "headers", None)
        if candidate:
            headers = candidate
            break
    host = _host(request_obj, headers)
    if not host:
        return WebSecurityDecision(
            allowed=False,
            status=503,
            code="web_security_host_missing",
            message="无法确认 WebUI 请求来源，已拒绝写操作",
        )

    origin = _header(headers, "Origin")
    referer = _header(headers, "Referer")
    if not origin and not referer:
        return WebSecurityDecision(
            allowed=False,
            status=403,
            code="web_security_origin_missing",
            message="缺少同源请求标识，已拒绝写操作",
        )
    if not any(
        _origin_matches_host(candidate, host)
        for candidate in (origin, referer)
        if candidate
    ):
        return WebSecurityDecision(
            allowed=False,
            status=403,
            code="web_security_origin_mismatch",
            message="WebUI 请求来源非法，已拒绝写操作",
        )
    return WebSecurityDecision(allowed=True)
