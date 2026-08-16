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
        "capture/index/status",
        "_api_capture_index_status",
        ("GET",),
        "获取偷取表情包分类索引进度",
        capability="catalog_index",
    ),
    WebRouteSpec(
        "capture/duplicates/ignore",
        "_api_capture_ignore_duplicates",
        ("POST",),
        "忽略重复捕获记录",
        capability="catalog_index",
    ),
    WebRouteSpec(
        "capture/items/dispose",
        "_api_capture_dispose_items",
        ("POST",),
        "删除或忽略捕获表情并加入黑名单",
        capability="catalog_index",
    ),
    WebRouteSpec(
        "capture/items/ignore-all",
        "_api_capture_ignore_all_items",
        ("POST",),
        "忽略当前资源包全部待处理和重复捕获记录",
        capability="catalog_index",
    ),
    WebRouteSpec(
        "capture/reindex",
        "_api_capture_reindex",
        ("POST",),
        "手动全量语义重索引表情包",
        capability="catalog_index",
    ),
    WebRouteSpec(
        "capture/reindex/status",
        "_api_capture_reindex_status",
        ("GET",),
        "获取表情包重索引进度",
        capability="catalog_index",
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
)


def enabled_route_specs(capabilities) -> tuple[WebRouteSpec, ...]:
    """Return the route specs whose capability is in the enabled set."""
    enabled = {str(item) for item in capabilities}
    return tuple(spec for spec in ROUTES if spec.capability in enabled)
