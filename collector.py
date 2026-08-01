"""Pure helpers for the meme-stealing pipeline.

This module intentionally has no AstrBot imports so its safety rules can be
tested on a normal Python installation.
"""

from __future__ import annotations

import asyncio
import ast
import json
from ipaddress import ip_address
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


FILTER_REPLY_LOCK_EXTRA = "astrbot_plugin_filter_reply_lock"


async def wait_for_filter_reply_lock(event, timeout: float = 30.0) -> str:
    """Wait until Filter finishes all follow-up text messages for this event."""
    getter = getattr(event, "get_extra", None)
    if not callable(getter):
        return "missing"
    try:
        reply_lock = getter(FILTER_REPLY_LOCK_EXTRA)
    except Exception:
        return "missing"
    if not isinstance(reply_lock, asyncio.Lock):
        return "missing"
    if not reply_lock.locked():
        return "released"

    try:
        await asyncio.wait_for(
            reply_lock.acquire(),
            timeout=max(0.0, float(timeout)),
        )
    except asyncio.TimeoutError:
        return "timeout"
    reply_lock.release()
    return "released"


OUTGOING_CATEGORY_PROMPT = """
你是表情包情景分类器。
根据用户消息和机器人回复，判断是否主动发送表情包；若发送，只能从候选分类中选择一个最合适的 category。
普通聊天可以主动发送表情包，不需要用户明确索要。
explicit_request=true 表示用户明确索要表情包，此时必须发送，should_send 必须为 true。
explicit_request=false 只表示本轮不是强制请求，不代表禁止发送，也不得仅以“用户未明确索要表情包”为理由拒绝发送。
当机器人回复包含明显的社交情绪或反应，例如惊讶、开心、赞叹、调侃、吐槽、安慰、尴尬或无奈时，应优先令 should_send=true。
只有纯事实说明、长篇严肃内容、错误提示或完全没有情绪反应时，才令 should_send=false。
输出一个 JSON 对象，字段必须为：should_send（布尔值）、category（字符串，发送时必须是候选分类之一）、confidence（0 到 1 的数字）、reason（不超过20字的字符串）。
不要输出 Markdown 或额外解释。
""".strip()


CATEGORY_ALIASES = {
    "生气": "angry",
    "愤怒": "angry",
    "开心": "happy",
    "高兴": "happy",
    "快乐": "happy",
    "难过": "sad",
    "伤心": "sad",
    "惊讶": "surprised",
    "震惊": "surprised",
    "困惑": "confused",
    "疑惑": "confused",
    "暧昧": "color",
    "卡顿": "cpu",
    "自嘲": "fool",
    "要钱": "givemoney",
    "喜欢": "like",
    "偷看": "see",
    "害羞": "shy",
    "工作": "work",
    "回复": "reply",
    "卖萌": "meow",
    "笨蛋": "baka",
    "早安": "morning",
    "睡觉": "sleep",
    "无奈": "sigh",
    "叹气": "sigh",
}


BLOCKED_AGENT_TOOLS_AFTER_MEME = frozenset({
    "astrbot_execute_python",
    "send_message_to_user",
})


def drop_empty_text_components(components: Sequence[Any]) -> list[Any]:
    """Remove blank text components while preserving images and other parts."""
    return [
        component
        for component in components
        if not hasattr(component, "text")
        or bool(str(getattr(component, "text", "") or "").strip())
    ]


def vision_failure_result() -> dict[str, Any]:
    """Represent an unavailable vision model as a high-confidence rejection."""
    return {
        "is_meme": False,
        "confidence": 1.0,
        "description": "视觉模型不可用",
        "vision_error": True,
    }


def should_skip_meme_result(
    vision: Any,
    rejection_confidence: float = 0.7,
) -> bool:
    """Fail closed when a vision result is missing or semantically invalid."""
    if not isinstance(vision, Mapping) or vision.get("vision_error"):
        return True

    raw_is_meme = vision.get("is_meme")
    if isinstance(raw_is_meme, bool):
        is_meme = raw_is_meme
    elif isinstance(raw_is_meme, str):
        normalized = raw_is_meme.strip().lower()
        if normalized in {"true", "yes", "1"}:
            is_meme = True
        elif normalized in {"false", "no", "0"}:
            is_meme = False
        else:
            return True
    else:
        return True

    try:
        confidence = float(vision.get("confidence"))
    except (TypeError, ValueError):
        return True
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        return True

    if is_meme:
        return False
    return confidence >= rejection_confidence


def is_safe_remote_image_url(value: Any) -> bool:
    """Allow only credential-free HTTP(S) URLs with public IP literals."""
    try:
        parsed = urlparse(str(value or "").strip())
        hostname = parsed.hostname
        if parsed.scheme.lower() not in {"http", "https"}:
            return False
        if not hostname or parsed.username or parsed.password:
            return False
        if hostname.lower() in {"localhost", "localhost.localdomain"}:
            return False
        try:
            return ip_address(hostname).is_global
        except ValueError:
            # DNS names are checked again after resolution in main.py.
            return True
    except ValueError:
        return False


def is_supported_image_source(value: Any) -> bool:
    """Return whether an image source uses a protocol the plugin understands.

    This is deliberately only a protocol/shape check.  Remote URLs still need
    the DNS/rebinding checks performed by the downloader, and local files must
    be checked against the caller's allowed directories before opening them.
    """
    source = str(value or "").strip()
    if not source:
        return False
    if source.startswith(("data:image/", "base64://")):
        return True
    parsed = urlparse(source)
    scheme = parsed.scheme.lower()
    if scheme in {"http", "https"}:
        return is_safe_remote_image_url(source)
    if scheme == "file":
        return bool(parsed.path)
    if scheme:
        return False
    return Path(source).is_absolute()


def complete_batch_indices(actual: Any, expected: Any) -> bool:
    """Return whether a batch response contains exactly the requested indices."""
    try:
        return set(actual) == set(expected)
    except TypeError:
        return False


def should_block_agent_tool_after_meme(tool_name: Any) -> bool:
    """Return whether a tool can create/send a second image after a local meme."""
    return str(tool_name or "").strip() in BLOCKED_AGENT_TOOLS_AFTER_MEME


def configured_provider_id(config, key: str, fallback_key: str = "") -> str:
    """Read a provider override and optionally fall back to another setting.

    Accepts either the raw config mapping or the typed ``PluginConfig``.
    """
    if isinstance(config, Mapping):
        primary = str(config.get(key, "") or "").strip()
        if primary:
            return primary
        return str(config.get(fallback_key, "") or "").strip() if fallback_key else ""
    primary = str(getattr(config, key, "") or "").strip()
    if primary:
        return primary
    return str(getattr(config, fallback_key, "") or "").strip() if fallback_key else ""


def strip_meme_markers(text: str) -> str:
    """Remove meme_manager_master's inline markers before its sender sees them."""
    return re.sub(r"&&[A-Za-z0-9_-]+&&", "", str(text or "")).strip()


def extract_meme_markers(text: str) -> list[str]:
    """Return unique meme_manager_master categories in marker order."""
    return list(dict.fromkeys(re.findall(r"&&([A-Za-z0-9_-]+)&&", str(text or ""))))


def explicit_meme_request(text: str) -> bool:
    """Detect a direct meme request while preserving later positive clauses."""
    value = str(text or "").strip()
    if not value:
        return False
    negative = (
        r"(?:不要|别|不用|无需|不需要|不想)\s*(?:再\s*)?(?:发|发送|来|换)\s*(?:一个|一张|个|张)?"
        r"|(?:不要|别|不用|无需|不需要|不想).{0,8}(?:发|发送|来).{0,12}"
        r"(?:表情包|表情|图片|图)"
    )

    def is_positive_clause(clause: str) -> bool:
        return bool(
            re.search(
                r"(?:发|发送|来|给我|请|可以|能不能|能否).{0,20}(?:表情包|表情|图片|图|meme)",
                clause,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"(?:表情包|表情|图片|图).{0,8}(?:发|发送|来)",
                clause,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"^\s*(?:再|继续)\s*(?:发|发送|来)\s*(?:一个|一张|个|张)(?:吧|呗|啊|呀|哦|喔)?\s*$",
                clause,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"^\s*换\s*(?:一个|一张|个|张)(?:吧|呗|啊|呀|哦|喔)?\s*$",
                clause,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"换\s*(?:一个|一张|个|张)\s*(?:表情包|表情|图片|图|meme)",
                clause,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"(?:再\s*)?(?:发|发送|来|换)\s*(?:一个|一张|个|张)?\s*"
                r"[\u4e00-\u9fffA-Za-z0-9 _-]{0,24}"
                r"(?:表情包|表情|图片|图|meme|猫猫|猫咪)",
                clause,
                flags=re.IGNORECASE,
            )
        )

    # A message may reject one target and request another in the same turn.
    # Evaluate clauses independently so "别发猫图，发个笨蛋表情" remains explicit.
    clauses = re.split(r"[，,。；;！!？?~～\n]+", value)
    return any(
        is_positive_clause(clause)
        and not re.search(negative, clause, flags=re.IGNORECASE)
        for clause in clauses
        if clause.strip()
    )


def is_meme_follow_up_request(text: str, *, recent_meme: bool) -> bool:
    """Recognize another-meme requests with an optional description.

    Users commonly say things such as ``再发一个可爱猫猫`` instead of the
    short ``再来一个``.  This check runs only when a meme was recently sent,
    and rejects common non-meme targets so ordinary follow-up requests do not
    enter the image-sending path.
    """
    if not recent_meme:
        return False
    value = str(text or "").strip()
    if not value or re.search(r"^(?:不要|别|不用|无需|不需要|不想|不要了)", value):
        return False
    value = re.sub(r"[。！!？?，,、~～\s]+$", "", value)
    if re.search(r"(?:文件|文档|链接|代码|答案|消息|文字|视频|音频|模型)", value):
        return False
    return bool(
        re.fullmatch(
            r"(?:还有(?:(?:别的|其他|另外)?(?:一个|一张|个|张)?"
            r"[\u4e00-\u9fffA-Za-z0-9 _-]{0,24}(?:吗|呢|没有)?)?|"
            r"(?:再发|再来|换)(?:一个|一张|个|张)?"
            r"[\u4e00-\u9fffA-Za-z0-9 _-]{0,24})",
            value,
            flags=re.IGNORECASE,
        )
    )


def contains_meme_send_claim(text: str) -> bool:
    """Detect a completed claim that a meme/image was sent.

    This deliberately does not match future or conditional wording such as
    ``我可以发一个表情包吗``.  It is used as a receipt guard for generated
    replies, not as a general meme request detector.
    """
    value = str(text or "").strip()
    if not value:
        return False
    meme = r"(?:表情包|表情|图片|猫猫|猫咪|这张图|这张图片)"
    return bool(
        re.search(
            rf"{meme}.{{0,16}}(?:发|发送|送)(?:给你|给我|了|啦|出去|好了)",
            value,
            flags=re.IGNORECASE,
        )
        or re.search(
            rf"(?:发|发送|送)(?:了|啦|给你|给我|出去|好了).{{0,16}}{meme}",
            value,
            flags=re.IGNORECASE,
        )
        or re.search(
            rf"(?:已经|已|刚刚|刚才|这就).{{0,4}}(?:发|发送|送|发出|送出)"
            rf".{{0,16}}{meme}",
            value,
            flags=re.IGNORECASE,
        )
    )


def should_block_agent_tool_for_meme_request(
    tool_name: Any,
    message_text: str = "",
    *,
    guard_active: bool = False,
) -> bool:
    """Block image-producing Agent tools for a meme request or active guard."""
    if not should_block_agent_tool_after_meme(tool_name):
        return False
    return bool(guard_active or explicit_meme_request(message_text))


def _read_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def group_id_from_event(event: Any) -> str:
    group_id = _read_value(event, "group_id", "")
    if not group_id:
        message_obj = _read_value(event, "message_obj")
        group_id = _read_value(message_obj, "group_id", "")
    return str(group_id or "").strip()


def event_identity(event: Any) -> str:
    """Return a stable identity for one incoming message event."""
    umo = str(_read_value(event, "unified_msg_origin", "") or "").strip()
    objects = [event, _read_value(event, "message_obj"), _read_value(event, "message")]
    for current in objects:
        if current is None:
            continue
        for field in ("message_id", "msg_id", "event_id", "id"):
            value = _read_value(current, field, "")
            if value not in (None, ""):
                return f"{umo}:{field}:{value}"
    return f"{umo}:object:{id(event)}"


def whitelist_allows(event: Any, whitelist: Sequence[str] | None) -> bool:
    """Return whether a group event matches an empty-or-explicit whitelist."""
    entries = {str(item).strip() for item in (whitelist or []) if str(item).strip()}
    if not entries:
        return True
    group_id = group_id_from_event(event)
    umo = str(_read_value(event, "unified_msg_origin", "") or "").strip()
    return bool(group_id and (group_id in entries or umo in entries))


def extract_image_sources(components: Sequence[Any]) -> list[str]:
    """Extract image locators from AstrBot message components or test mappings."""
    sources: list[str] = []
    for component in components:
        component_type = str(
            _read_value(component, "type", "")
            or component.__class__.__name__
        ).lower()
        if "image" not in component_type:
            continue
        for field in ("url", "file", "path", "src", "data", "base64"):
            value = _read_value(component, field)
            if isinstance(value, str) and value.strip():
                sources.append(value.strip())
                break
    return sources


def parse_model_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model response, including fenced output."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("model response is empty")
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", candidate, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model response does not contain a JSON object") from None
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            try:
                parsed = ast.literal_eval(candidate[start : end + 1])
            except (SyntaxError, ValueError) as literal_exc:
                raise ValueError("model response contains invalid JSON") from literal_exc
    if not isinstance(parsed, dict):
        raise ValueError("model response is not a JSON object")
    return parsed


def normalize_category(
    raw_category: Any,
    allowed_categories: set[str],
    fallback: str = "confused",
) -> str:
    """Map model output to a safe existing category, never to a path."""
    allowed = {
        str(item).strip()
        for item in allowed_categories
        if _is_safe_category(str(item).strip())
    }
    fallback = fallback if _is_safe_category(fallback) and fallback in allowed else (
        sorted(allowed)[0] if allowed else "confused"
    )
    raw = str(raw_category or "").strip().strip("`'\"").lower()
    normalized = CATEGORY_ALIASES.get(raw, raw)
    if normalized in allowed and "/" not in normalized and "\\" not in normalized:
        return normalized
    return fallback


def _is_safe_category(value: str) -> bool:
    return bool(value and re.fullmatch(r"[A-Za-z0-9_-]+", value))
