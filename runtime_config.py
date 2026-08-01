"""Typed, immutable runtime configuration for meme_manager_master.

``PluginConfig`` is the single source of truth for every runtime setting:
defaults, value bounds, legacy-key migration, and the AstrBot config schema.
Business code reads attributes, never scattered string keys.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Mapping


SLOTS_SUPPORTED = sys.version_info >= (3, 10)

_MIGRATION_USED = False


def _frozen_dataclass(*, slots: bool = False):
    """dataclass(frozen=True) that tolerates Python 3.9 (no slots kwarg)."""
    if SLOTS_SUPPORTED:
        return dataclass(frozen=True, slots=slots)
    return dataclass(frozen=True)


def bool_value(raw: Any, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    if isinstance(raw, str):
        return raw.strip().lower() not in {"", "0", "false", "no", "off"}
    return default


def int_value(raw: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(raw, bool):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def float_value(raw: Any, default: float, minimum: float, maximum: float) -> float:
    if isinstance(raw, bool):
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def string_value(raw: Any, default: str) -> str:
    if raw is None:
        return default
    return str(raw)


def list_value(raw: Any, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if isinstance(raw, str):
        return tuple(item.strip() for item in re.split(r"[,\n]", raw) if item.strip())
    if isinstance(raw, (list, tuple)):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    return tuple(default)


def consume_migration_used() -> bool:
    """Return and clear whether a legacy config key supplied a value."""
    global _MIGRATION_USED
    used = _MIGRATION_USED
    _MIGRATION_USED = False
    return used


# Legacy nested paths consulted before the legacy flat keys for a typed field.
_LEGACY_PATHS: dict[str, tuple[tuple[str, ...], ...]] = {
    "vision_provider_id": (("semantic", "vision_provider_id"),),
    "scene_provider_id": (("semantic", "scene_provider_id"),),
    "reply_scene_provider_id": (("semantic", "reply_scene_provider_id"),),
    "library_index_provider_id": (("semantic", "library_index_provider_id"),),
    "vector_semantic_enabled": (("semantic", "enabled"),),
}


@_frozen_dataclass(slots=True)
class PluginConfig:
    enabled: bool = True
    group_whitelist: tuple[str, ...] = ()
    vision_provider_id: str = ""
    scene_provider_id: str = ""
    reply_scene_provider_id: str = ""
    only_capture_memes: bool = True
    meme_rejection_confidence: float = 0.7
    max_images_per_message: int = 2
    max_concurrent: int = 2
    max_image_size_mb: int = 10
    download_timeout: float = 20.0
    auto_send_enabled: bool = True
    auto_send_probability: float = 50.0
    auto_send_cooldown: float = 30.0
    auto_send_candidate_limit: int = 8
    meme_repeat_window: float = 300.0
    meme_follow_up_window: float = 300.0
    proactive_send_after_steal: bool = False
    perceptual_dedupe_enabled: bool = True
    perceptual_duplicate_threshold: int = 6
    library_index_enabled: bool = False
    library_index_provider_id: str = ""
    library_index_batch_size: int = 6
    library_index_progress_step: int = 5
    library_index_rename_files: bool = True
    health_check_interval: float = 300.0
    fallback_category: str = "confused"
    local_image_roots: tuple[str, ...] = ()
    vector_semantic_enabled: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PluginConfig":
        """Build the immutable config, honoring flat, legacy and defaults."""
        data = dict(raw or {})

        def lookup(
            key: str,
            legacy_paths: tuple[tuple[str, ...], ...] = (),
            legacy_keys: tuple[str, ...] = (),
        ) -> Any:
            global _MIGRATION_USED
            if key in data and data[key] is not None:
                return data[key]
            for path in legacy_paths:
                current: Any = data
                found = True
                for part in path:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        found = False
                        break
                if found and current is not None:
                    _MIGRATION_USED = True
                    return current
            for legacy_key in legacy_keys:
                if legacy_key in data and data[legacy_key] is not None:
                    _MIGRATION_USED = True
                    return data[legacy_key]
            return None

        def legacy_paths(key: str) -> tuple[tuple[str, ...], ...]:
            return _LEGACY_PATHS.get(key, ())

        return cls(
            enabled=bool_value(lookup("enabled"), True),
            group_whitelist=list_value(lookup("group_whitelist")),
            vision_provider_id=string_value(
                lookup("vision_provider_id", legacy_paths("vision_provider_id")), ""
            ),
            scene_provider_id=string_value(
                lookup("scene_provider_id", legacy_paths("scene_provider_id")), ""
            ),
            reply_scene_provider_id=string_value(
                lookup("reply_scene_provider_id", legacy_paths("reply_scene_provider_id")), ""
            ),
            only_capture_memes=bool_value(lookup("only_capture_memes"), True),
            meme_rejection_confidence=float_value(
                lookup("meme_rejection_confidence"), 0.7, 0, 1
            ),
            max_images_per_message=int_value(
                lookup("max_images_per_message"), 2, 1, 6
            ),
            max_concurrent=int_value(lookup("max_concurrent"), 2, 1, 8),
            max_image_size_mb=int_value(lookup("max_image_size_mb"), 10, 1, 50),
            download_timeout=float_value(lookup("download_timeout"), 20, 5, 120),
            auto_send_enabled=bool_value(lookup("auto_send_enabled"), True),
            auto_send_probability=float_value(
                lookup("auto_send_probability"), 50, 0, 100
            ),
            auto_send_cooldown=float_value(lookup("auto_send_cooldown"), 30, 0, 3600),
            auto_send_candidate_limit=int_value(
                lookup("auto_send_candidate_limit"), 8, 2, 16
            ),
            meme_repeat_window=float_value(
                lookup("meme_repeat_window"), 300, 0, 86400
            ),
            meme_follow_up_window=float_value(
                lookup("meme_follow_up_window"), 300, 10, 1800
            ),
            proactive_send_after_steal=bool_value(
                lookup("proactive_send_after_steal"), False
            ),
            perceptual_dedupe_enabled=bool_value(
                lookup("perceptual_dedupe_enabled"), True
            ),
            perceptual_duplicate_threshold=int_value(
                lookup("perceptual_duplicate_threshold"), 6, 0, 16
            ),
            library_index_enabled=bool_value(lookup("library_index_enabled"), False),
            library_index_provider_id=string_value(
                lookup("library_index_provider_id", legacy_paths("library_index_provider_id")),
                "",
            ),
            library_index_batch_size=int_value(
                lookup("library_index_batch_size"), 6, 1, 12
            ),
            library_index_progress_step=int_value(
                lookup("library_index_progress_step"), 5, 1, 50
            ),
            library_index_rename_files=bool_value(
                lookup("library_index_rename_files"), True
            ),
            health_check_interval=float_value(
                lookup("health_check_interval"), 300, 10, 600
            ),
            fallback_category=string_value(lookup("fallback_category"), "confused"),
            local_image_roots=list_value(lookup("local_image_roots")),
            vector_semantic_enabled=bool_value(
                lookup("vector_semantic_enabled", legacy_paths("vector_semantic_enabled")),
                False,
            ),
        )

    @classmethod
    def to_schema(cls) -> dict[str, Any]:
        """Return the AstrBot config schema, generated from this definition."""
        return {
            "enabled": {
                "type": "bool",
                "description": "启用表情包偷取",
                "hint": "关闭后暂停自动收集；手动命令仍可按插件逻辑使用。",
                "default": True,
            },
            "group_whitelist": {
                "type": "list",
                "items": {"type": "string"},
                "description": "群聊白名单",
                "hint": "填写群号或完整 UMO；留空表示允许所有群。",
                "default": [],
            },
            "vision_provider_id": {
                "type": "string",
                "description": "识图模型",
                "hint": "用于判断图片是否为表情包，必须支持图片输入；留空使用当前会话模型。",
                "_special": "select_provider",
                "default": "",
            },
            "scene_provider_id": {
                "type": "string",
                "description": "情景识别模型",
                "hint": "用于偷取分类和自动发送选图；留空使用当前会话模型。",
                "_special": "select_provider",
                "default": "",
            },
            "reply_scene_provider_id": {
                "type": "string",
                "description": "回复情景识别模型",
                "hint": "用于自动发送时判断回复情景；留空使用情景识别模型。",
                "_special": "select_provider",
                "default": "",
            },
            "only_capture_memes": {
                "type": "bool",
                "description": "只保存表情包",
                "hint": "开启后跳过普通照片和非表情图片，推荐保持开启。",
                "default": True,
            },
            "meme_rejection_confidence": {
                "type": "float",
                "description": "表情包判定拒绝置信度",
                "hint": "视觉模型置信度低于该值时判定为非表情包。",
                "default": 0.7,
                "min": 0,
                "max": 1,
            },
            "max_images_per_message": {
                "type": "int",
                "description": "单条消息最多偷取图片数",
                "hint": "限制一次处理的图片数量，避免群聊中一次性触发过多模型请求。",
                "default": 2,
                "min": 1,
                "max": 6,
            },
            "max_concurrent": {
                "type": "int",
                "description": "最大并发识别数",
                "hint": "同时进行视觉识别与分类的图片数量上限。",
                "default": 2,
                "min": 1,
                "max": 8,
            },
            "max_image_size_mb": {
                "type": "int",
                "description": "单张图片大小上限（MB）",
                "hint": "超过该大小的图片不会被下载或保存。",
                "default": 10,
                "min": 1,
                "max": 50,
            },
            "download_timeout": {
                "type": "float",
                "description": "图片下载超时（秒）",
                "hint": "下载远程图片的超时上限。",
                "default": 20,
                "min": 5,
                "max": 120,
            },
            "auto_send_enabled": {
                "type": "bool",
                "description": "根据情景自动发送",
                "hint": "开启后会根据用户消息和机器人回复判断是否发送合适的表情包。",
                "default": True,
            },
            "auto_send_probability": {
                "type": "float",
                "description": "自动发送概率",
                "hint": "普通对话中的自动发送概率；明确要求表情包时会强制尝试发送。",
                "default": 50,
                "min": 0,
                "max": 100,
            },
            "auto_send_cooldown": {
                "type": "float",
                "description": "自动发送冷却时间（秒）",
                "hint": "防止连续对话中短时间重复发送，0 表示不限制。",
                "default": 30,
                "min": 0,
                "max": 3600,
            },
            "auto_send_candidate_limit": {
                "type": "int",
                "description": "自动发送候选数量上限",
                "hint": "选图时考虑的候选表情包数量。",
                "default": 8,
                "min": 2,
                "max": 16,
            },
            "meme_repeat_window": {
                "type": "float",
                "description": "单图重复发送降权窗口（秒）",
                "hint": "最近发送过的图片会降低被自动选中的概率，0 表示关闭单图降权。",
                "default": 300,
                "min": 0,
                "max": 86400,
            },
            "meme_follow_up_window": {
                "type": "float",
                "description": "表情包后续请求窗口（秒）",
                "hint": "明确请求后的再次请求窗口，如“再来一个”。",
                "default": 300,
                "min": 10,
                "max": 1800,
            },
            "proactive_send_after_steal": {
                "type": "bool",
                "description": "偷取后主动发送",
                "hint": "收集到表情包后是否立即尝试匹配当前会话并主动发送。",
                "default": False,
            },
            "perceptual_dedupe_enabled": {
                "type": "bool",
                "description": "感知哈希去重",
                "hint": "开启后对相似图片进行感知去重，避免重复收集。",
                "default": True,
            },
            "perceptual_duplicate_threshold": {
                "type": "int",
                "description": "感知去重阈值",
                "hint": "0 关闭感知去重，数值越大判定越宽松。",
                "default": 6,
                "min": 0,
                "max": 16,
            },
            "library_index_enabled": {
                "type": "bool",
                "description": "后台补充表情包索引",
                "hint": "开启后后台为缺少描述的图片补充索引，可能产生额外模型调用；已有 index.json 不会被清空。",
                "default": False,
            },
            "library_index_provider_id": {
                "type": "string",
                "description": "后台索引模型",
                "hint": "用于后台补充 index.json 描述和分类索引；留空时使用识图模型。",
                "_special": "select_provider",
                "default": "",
            },
            "library_index_batch_size": {
                "type": "int",
                "description": "后台索引批大小",
                "hint": "每批补充索引的图片数量。",
                "default": 6,
                "min": 1,
                "max": 12,
            },
            "library_index_progress_step": {
                "type": "int",
                "description": "后台索引日志步长",
                "hint": "每处理多少张图片记录一次进度日志。",
                "default": 5,
                "min": 1,
                "max": 50,
            },
            "library_index_rename_files": {
                "type": "bool",
                "description": "索引时重命名文件",
                "hint": "开启后按分类为缺少描述的图片生成稳定文件名。",
                "default": True,
            },
            "health_check_interval": {
                "type": "float",
                "description": "健康检查间隔（秒）",
                "hint": "后台健康检查与依赖状态刷新的间隔。",
                "default": 300,
                "min": 10,
                "max": 600,
            },
            "fallback_category": {
                "type": "string",
                "description": "兜底分类",
                "hint": "情景识别失败或无法分类时使用的默认分类。",
                "default": "confused",
            },
            "local_image_roots": {
                "type": "list",
                "items": {"type": "string"},
                "description": "本地图片读取目录",
                "hint": "允许读取的本地图片根目录，用于发送本地表情包。",
                "default": [],
            },
            "vector_semantic_enabled": {
                "type": "bool",
                "description": "启用向量语义能力",
                "hint": "需要安装 faiss-cpu（见 requirements-semantic.txt）；关闭时默认路由面不暴露向量任务操作。",
                "default": False,
            },
        }
