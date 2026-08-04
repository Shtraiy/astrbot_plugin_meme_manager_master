"""Pure image decoding and validation used by the capture adapter."""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class DecodedImage:
    content: bytes
    extension: str


def payload_from_content(
    content: bytes,
    limit: int,
    detect_extension: Callable[[bytes], str | None],
) -> DecodedImage | None:
    if not content or len(content) > int(limit):
        return None
    extension = detect_extension(content)
    if extension is None:
        return None
    return DecodedImage(content=bytes(content), extension=str(extension))


def decode_base64_image(
    value: str,
    limit: int,
    detect_extension: Callable[[bytes], str | None],
) -> DecodedImage | None:
    try:
        content = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError):
        return None
    return payload_from_content(content, limit, detect_extension)


def decode_data_url_image(
    source: str,
    limit: int,
    detect_extension: Callable[[bytes], str | None],
) -> DecodedImage | None:
    match = re.match(r"data:image/([a-zA-Z0-9.+-]+);base64,(.+)", source, re.DOTALL)
    if not match:
        return None
    return decode_base64_image(match.group(2), limit, detect_extension)
