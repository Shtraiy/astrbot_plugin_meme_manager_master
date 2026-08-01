from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse

import aiohttp

from ..storage import detect_image_extension


@dataclass(frozen=True)
class ImageDownload:
    content: bytes
    extension: str


def is_safe_image_url(source: str) -> bool:
    """Apply syntax-level restrictions before any network request."""
    try:
        parsed = urlparse(str(source or "").strip())
        hostname = parsed.hostname
        parsed.port
    except (TypeError, ValueError):
        return False
    if parsed.scheme.lower() != "https" or not hostname:
        return False
    if parsed.username or parsed.password:
        return False
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        return False
    try:
        return ip_address(hostname).is_global
    except ValueError:
        return True


async def _remote_target_is_public(source: str) -> bool:
    if not is_safe_image_url(source):
        return False
    parsed = urlparse(source)
    hostname = parsed.hostname
    if not hostname:
        return False
    try:
        port = parsed.port or 443
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except (OSError, ValueError):
        return False
    resolved = {
        str(info[4][0]).split("%", 1)[0]
        for info in addresses
        if info and len(info) > 4 and info[4]
    }
    if not resolved:
        return False
    try:
        return all(ip_address(address).is_global for address in resolved)
    except ValueError:
        return False


def validate_image_payload(content: bytes, limit: int) -> ImageDownload | None:
    if not content or len(content) > limit:
        return None
    extension = detect_image_extension(content)
    if extension not in {".png", ".jpg", ".gif", ".webp"}:
        return None
    return ImageDownload(content, extension)


async def download_image(
    source: str,
    limit: int,
    *,
    timeout_seconds: int = 20,
) -> ImageDownload | None:
    if limit <= 0 or not await _remote_target_is_public(source):
        return None
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(source, allow_redirects=False) as response:
                status = int(getattr(response, "status", 0) or 0)
                if status < 200 or status >= 300:
                    return None
                raw_length = response.headers.get("Content-Length")
                if raw_length:
                    try:
                        if int(raw_length) > limit:
                            return None
                    except (TypeError, ValueError):
                        return None

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.content.iter_chunked(64 * 1024):
                    total += len(chunk)
                    if total > limit:
                        return None
                    chunks.append(chunk)
                return validate_image_payload(b"".join(chunks), limit)
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError):
        return None
