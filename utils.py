"""Small shared helpers used by the manager backend and capture runtime."""

from __future__ import annotations

import json
import logging
import os
import random
import string
from pathlib import Path
from typing import Any

from .backend.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)


def ensure_dir_exists(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)


def save_json(data: dict[str, Any], filepath: str) -> bool:
    try:
        atomic_write_json(Path(filepath), data)
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
