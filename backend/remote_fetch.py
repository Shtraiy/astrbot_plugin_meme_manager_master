"""Shared policy helpers for bounded, public HTTPS downloads."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator
from ipaddress import ip_address
from urllib.parse import ParseResult, urlparse


def parse_public_https_url(source: str) -> ParseResult | None:
    """Return a parsed URL only when it is safe to use as a public target."""
    try:
        parsed = urlparse(str(source or "").strip())
        hostname = parsed.hostname
        parsed.port
    except (TypeError, ValueError):
        return None
    if parsed.scheme.lower() != "https" or not hostname:
        return None
    if parsed.username or parsed.password:
        return None
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        return None
    try:
        if not ip_address(hostname).is_global:
            return None
    except ValueError:
        pass
    return parsed


def is_public_https_url(source: str) -> bool:
    return parse_public_https_url(source) is not None


def bounded_chunks(chunks: Iterable[bytes], limit: int) -> Iterator[bytes]:
    """Yield response chunks and fail before a stream exceeds its byte limit."""
    if limit <= 0:
        raise ValueError("remote response limit must be positive")
    total = 0
    for chunk in chunks:
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            raise ValueError("remote response exceeds size limit")
        yield chunk


async def bounded_async_chunks(
    chunks: AsyncIterable[bytes], limit: int
) -> AsyncIterator[bytes]:
    """Async equivalent used by aiohttp response bodies."""
    if limit <= 0:
        raise ValueError("remote response limit must be positive")
    total = 0
    async for chunk in chunks:
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            raise ValueError("remote response exceeds size limit")
        yield chunk
