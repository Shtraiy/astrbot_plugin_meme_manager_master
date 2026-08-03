"""Declarative WebUI route table with capability gates.

Every route is a ``WebRouteSpec``; the capability field decides whether it is
registered.  The default surface is ``{"core", "catalog_index"}``; vector
semantic task routes are only registered when the ``vector_semantic``
capability is explicitly enabled (config + available FAISS).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass


SLOTS_SUPPORTED = sys.version_info >= (3, 10)


def _frozen_dataclass(*, slots: bool = False):
    """dataclass(frozen=True) that tolerates Python 3.9 (no slots kwarg)."""
    if SLOTS_SUPPORTED:
        return dataclass(frozen=True, slots=slots)
    return dataclass(frozen=True)


@_frozen_dataclass(slots=True)
class WebRouteSpec:
    path: str
    handler_name: str
    methods: tuple[str, ...]
    description: str
    capability: str = "core"


ROUTES: tuple[WebRouteSpec, ...] = (
    WebRouteSpec("emoji", "_api_get_emojis", ("GET",), "获取所有分类的表情列表"),
    WebRouteSpec(
        "emoji/<category>",
        "_api_get_emoji_by_category",
        ("GET",),
        "获取某个分类下的表情",
    ),
    WebRouteSpec(
        "emoji/add/<category>",
        "_api_add_emoji",
        ("POST",),
        "上传表情到指定分类（表单字段 file）",
    ),
    WebRouteSpec("emoji/delete", "_api_delete_emoji", ("POST",), "删除单个表情"),
    WebRouteSpec(
        "emoji/batch_delete", "_api_batch_delete_emojis", ("POST",), "批量删除表情"
    ),
    WebRouteSpec(
        "emoji/move", "_api_move_emoji", ("POST",), "移动单个表情到其他分类"
    ),
    WebRouteSpec(
        "emoji/batch_move", "_api_batch_move_emojis", ("POST",), "批量移动表情"
    ),
    WebRouteSpec(
        "emoji/batch_copy", "_api_batch_copy_emojis", ("POST",), "批量复制表情"
    ),
    WebRouteSpec(
        "emoji/clear_all",
        "_api_clear_all_emojis",
        ("POST",),
        "清空所有表情（保留分类）",
    ),
    WebRouteSpec("emotions", "_api_get_emotions", ("GET",), "获取分类描述"),
    WebRouteSpec(
        "capture/workspace",
        "_api_capture_workspace",
        ("GET",),
        "获取偷取表情包索引工作台数据",
        capability="catalog_index",
    ),
    WebRouteSpec(
        "capture/index",
        "_api_capture_index",
        ("POST",),
        "手动处理偷取表情包分类索引",
        capability="catalog_index",
    ),
    WebRouteSpec(
        "capture/reindex",
        "_api_capture_reindex",
        ("POST",),
        "只重新编号并同步表情包索引",
        capability="catalog_index",
    ),
    WebRouteSpec(
        "category/delete", "_api_delete_category", ("POST",), "删除分类及其文件"
    ),
    WebRouteSpec(
        "category/clear", "_api_clear_category", ("POST",), "清空分类内表情（保留分类）"
    ),
    WebRouteSpec(
        "category/restore", "_api_restore_category", ("POST",), "恢复或创建分类"
    ),
    WebRouteSpec(
        "category/rename", "_api_rename_category", ("POST",), "重命名分类"
    ),
    WebRouteSpec(
        "category/update_description",
        "_api_update_description",
        ("POST",),
        "更新分类描述",
    ),
    WebRouteSpec(
        "category/remove_from_config",
        "_api_remove_from_config",
        ("POST",),
        "仅从配置中移除分类",
    ),
    WebRouteSpec("sync/status", "_api_sync_status", ("GET",), "获取配置同步状态"),
    WebRouteSpec(
        "sync/config", "_api_sync_config", ("POST",), "同步配置与文件系统"
    ),
    WebRouteSpec(
        "meme_image", "_api_serve_meme_image", ("GET",), "直接返回表情图片文件"
    ),
    WebRouteSpec(
        "meme_image_data",
        "_api_get_meme_image_data",
        ("GET",),
        "获取表情图片的 Data URL（预览）",
    ),
    WebRouteSpec("packs", "_api_list_packs", ("GET",), "获取已安装表情包列表"),
    WebRouteSpec(
        "packs/<pack_id>", "_api_get_pack_detail", ("GET",), "获取单个表情包详情"
    ),
    WebRouteSpec(
        "packs/default", "_api_set_default_pack", ("POST",), "设置默认表情包"
    ),
    WebRouteSpec(
        "packs/export", "_api_export_pack", ("POST",), "导出表情包压缩文件"
    ),
    WebRouteSpec(
        "packs/export/status",
        "_api_pack_export_status",
        ("GET",),
        "获取表情包可导出能力",
    ),
    WebRouteSpec(
        "packs/export/download",
        "_api_download_pack",
        ("GET",),
        "导出并下载表情包压缩文件",
    ),
    WebRouteSpec("packs/import", "_api_import_pack", ("POST",), "导入表情包压缩文件"),
    WebRouteSpec(
        "packs/import/stage",
        "_api_stage_pack_import",
        ("POST",),
        "上传并预检表情包压缩文件",
    ),
    WebRouteSpec(
        "packs/import/apply",
        "_api_apply_pack_import",
        ("POST",),
        "确认导入已预检的表情包",
    ),
    WebRouteSpec(
        "packs/uninstall", "_api_uninstall_pack", ("POST",), "卸载表情包"
    ),
    WebRouteSpec(
        "community/index/fetch",
        "_api_fetch_community_index",
        ("POST",),
        "拉取并缓存社区索引",
    ),
    WebRouteSpec(
        "community/index/cache",
        "_api_get_cached_community_index",
        ("GET",),
        "读取已缓存的社区索引",
    ),
    WebRouteSpec(
        "community/install",
        "_api_install_community_pack",
        ("POST",),
        "按社区 source 安装表情包",
    ),
    WebRouteSpec(
        "community/install_official_first",
        "_api_install_official_first_pack",
        ("POST",),
        "安装官方首个表情包",
    ),
    WebRouteSpec(
        "settings/rules",
        "_api_settings_rules",
        ("GET", "POST"),
        "获取或保存表情包选择规则",
    ),
    WebRouteSpec(
        "settings/targets",
        "_api_settings_targets",
        ("GET",),
        "获取规则 target 建议值",
    ),
    WebRouteSpec(
        "settings/backup/export",
        "_api_export_runtime_backup",
        ("POST",),
        "导出运行时全量备份",
    ),
    WebRouteSpec(
        "settings/backup/import",
        "_api_import_runtime_backup",
        ("POST",),
        "导入运行时全量备份",
    ),
)


def enabled_route_specs(capabilities) -> tuple[WebRouteSpec, ...]:
    """Return the route specs whose capability is in the enabled set."""
    enabled = {str(item) for item in capabilities}
    return tuple(spec for spec in ROUTES if spec.capability in enabled)
