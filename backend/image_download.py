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
    return bool(await _resolve_public_addresses(source))


async def _resolve_public_addresses(source: str) -> tuple[str, ...]:
    if not is_safe_image_url(source):
        return ()
    parsed = urlparse(source)
    hostname = parsed.hostname
    if not hostname:
        return ()
    try:
        port = parsed.port or 443
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except (OSError, ValueError):
        return ()
    resolved = {
        str(info[4][0]).split("%", 1)[0]
        for info in addresses
        if info and len(info) > 4 and info[4]
    }
    if not resolved:
        return ()
    try:
        parsed_addresses = {ip_address(address) for address in resolved}
    except ValueError:
        return ()
    if not parsed_addresses or not all(address.is_global for address in parsed_addresses):
        return ()
    return tuple(sorted(str(address) for address in parsed_addresses))


class _PinnedPublicResolver:
    """aiohttp resolver that only returns the IPs checked before connecting."""

    def __init__(self, hostname: str, port: int, addresses: tuple[str, ...]):
        self.hostname = hostname
        self.port = port
        self.addresses = tuple(addresses)

    async def resolve(self, hostname: str, port: int = 443, family: int = 0):
        if hostname != self.hostname or port != self.port:
            return []
        return [
            {
                "hostname": hostname,
                "host": address,
                "port": port,
                "family": family,
                "proto": 0,
                "flags": 0,
            }
            for address in self.addresses
        ]

    async def close(self) -> None:
        return None


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
    if limit <= 0:
        return None
    checked_addresses = await _resolve_public_addresses(source)
    if not checked_addresses:
        return None
    parsed = urlparse(source)
    hostname = parsed.hostname
    port = parsed.port or 443
    resolver = _PinnedPublicResolver(hostname, port, checked_addresses)
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    try:
        connector_factory = getattr(aiohttp, "TCPConnector", None)
        connector = (
            connector_factory(resolver=resolver, ssl=True)
            if connector_factory is not None
            else None
        )
        session_kwargs = {"timeout": timeout}
        if connector is not None:
            session_kwargs["connector"] = connector
        async with aiohttp.ClientSession(**session_kwargs) as session:
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
