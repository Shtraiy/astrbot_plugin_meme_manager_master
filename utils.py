"""Small shared helpers used by the manager backend and capture runtime."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import string
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


def ensure_dir_exists(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)


def save_json(data: dict[str, Any], filepath: str) -> bool:
    try:
        ensure_dir_exists(os.path.dirname(filepath))
        with open(filepath, "w", encoding="utf-8") as file_obj:
            json.dump(data, file_obj, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        logger.error("保存 JSON 文件失败 %s: %s", filepath, exc)
        return False


def load_json(filepath: str, default: dict | None = None) -> dict:
    try:
        with open(filepath, encoding="utf-8") as file_obj:
            value = json.load(file_obj)
        return value if isinstance(value, dict) else (default or {})
    except Exception as exc:
        logger.debug("加载 JSON 文件失败 %s: %s", filepath, exc)
        return default if default is not None else {}


def dict_to_string(dictionary: dict) -> str:
    return "\n".join(f"{key} - {value}\n" for key, value in dictionary.items())


def normalize_probability(value: Any) -> int:
    try:
        probability = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, probability))


def probability_hit(value: Any, roll: int | None = None) -> bool:
    probability = normalize_probability(value)
    if probability <= 0:
        return False
    if probability >= 100:
        return True
    actual_roll = random.randint(1, 100) if roll is None else int(roll)
    return actual_roll <= probability


def generate_secret_key(length: int = 8) -> str:
    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for _ in range(length))


async def get_public_ip() -> str:
    """Best-effort public IPv4 lookup used by optional integrations."""
    ipv4_apis = (
        "http://ipv4.ifconfig.me/ip",
        "http://api-ipv4.ip.sb/ip",
        "http://v4.ident.me",
        "http://ip.qaros.com",
        "http://ipv4.icanhazip.com",
        "http://4.icanhazip.com",
    )
    async with aiohttp.ClientSession() as session:
        for api in ipv4_apis:
            try:
                async with session.get(api, timeout=5) as response:
                    if response.status != 200:
                        continue
                    value = (await response.text()).strip()
                    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value):
                        return value
            except Exception:
                continue
    return "[server-public-ip-unavailable]"
