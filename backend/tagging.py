"""Controlled vocabulary and normalization for meme tags."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


CANONICAL_TAGS: tuple[str, ...] = (
    "开心",
    "愤怒",
    "悲伤",
    "震惊",
    "疑惑",
    "尴尬",
    "害怕",
    "期待",
    "无语",
    "赞同",
    "拒绝",
    "嘲讽",
    "嫌弃",
    "感谢",
    "道歉",
    "安慰",
    "催促",
    "围观",
    "吃瓜",
    "摸鱼",
    "庆祝",
    "工作",
    "加班",
    "睡觉",
    "早安",
    "求助",
    "发钱",
    "其他",
)
MAX_TAGS = 5

_ALIASES: dict[str, str] = {
    "生气": "愤怒",
    "发火": "愤怒",
    "恼火": "愤怒",
    "吃惊": "震惊",
    "惊讶": "震惊",
    "意外": "震惊",
    "困惑": "疑惑",
    "懵": "疑惑",
    "难过": "悲伤",
    "伤心": "悲伤",
    "高兴": "开心",
    "快乐": "开心",
    "无奈": "无语",
    "喜欢": "赞同",
    "同意": "赞同",
    "反对": "拒绝",
    "生硬嘲笑": "嘲讽",
    "催回复": "催促",
    "看戏": "围观",
    "围观吃瓜": "吃瓜",
    "休息": "睡觉",
    "早上好": "早安",
    "要钱": "发钱",
    "求回应": "求助",
    # Existing English category names.
    "happy": "开心",
    "angry": "愤怒",
    "sad": "悲伤",
    "surprised": "震惊",
    "confused": "疑惑",
    "reply": "求助",
    "sigh": "无语",
    "morning": "早安",
    "sleep": "睡觉",
    "work": "工作",
    "givemoney": "发钱",
    "like": "赞同",
    "see": "围观",
    "shy": "尴尬",
    "fool": "嘲讽",
    "baka": "嘲讽",
    "meow": "安慰",
    "cpu": "疑惑",
    "color": "无语",
}

_CANONICAL_BY_KEY = {
    unicodedata.normalize("NFKC", tag).casefold(): tag for tag in CANONICAL_TAGS
}
_ALIAS_BY_KEY = {
    unicodedata.normalize("NFKC", key).casefold(): value
    for key, value in _ALIASES.items()
}


def tag_aliases() -> dict[str, str]:
    """Return a copy of the accepted alias-to-canonical mapping."""
    return dict(_ALIASES)


def canonical_tag(value: Any) -> str | None:
    """Resolve one value to a canonical tag, or return ``None``."""
    raw = unicodedata.normalize("NFKC", str(value or "")).strip(" `\"'\t\r\n")
    if not raw:
        return None
    key = raw.casefold()
    return _CANONICAL_BY_KEY.get(key) or _ALIAS_BY_KEY.get(key)


def _tag_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part for part in re.split(r"[,，、;；|/\s]+", value) if part]
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_tag_values(item))
        return values
    return []


def normalize_tags(value: Any, *, fallback: str = "其他") -> list[str]:
    """Normalize arbitrary model/user values to at most five known tags."""
    found = {tag for item in _tag_values(value) if (tag := canonical_tag(item))}
    ordered = [tag for tag in CANONICAL_TAGS if tag in found]
    if not ordered:
        fallback_tag = canonical_tag(fallback) or "其他"
        return [fallback_tag]
    return ordered[:MAX_TAGS]
