"""User-visible reply policy for successful meme dispatches."""

from __future__ import annotations


def success_reply_text(existing_text: str | None = None) -> str:
    """Preserve meaningful Agent text and emit no canned success caption."""
    value = str(existing_text or "")
    return value if value.strip() else ""
