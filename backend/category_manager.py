from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import (
    ACTIVE_PACK_MANIFEST_PATH,
    MEMES_DATA_PATH,
    MEMES_DIR,
    sync_pack_metadata,
    get_active_pack_paths,
)
from ..utils import ensure_dir_exists, load_json, save_json
from ..storage import MemeStore, is_safe_category_segment
from .tagging import canonical_tag
from .pack_repository import PackRepository
from .semantic_compat import invalidate_semantic_metadata

logger = logging.getLogger(__name__)


def _reconcile_pack_catalogs(pack_dir: Path) -> None:
    """Keep one pack's compatibility indexes in sync."""
    try:
        MemeStore(Path(pack_dir).resolve()).reconcile_catalogs()
    except Exception as exc:
        logger.warning("同步分类索引失败: %s", exc, exc_info=True)


def is_safe_category_name(category: str) -> bool:
    """Return whether category stays within one memes directory segment."""
    return is_safe_category_segment(category)


class CategoryManager:
    def _active_paths(self) -> dict[str, Path | str]:
        if self.pack_dir is not None:
            return {
                "pack_id": self.pack_dir.name,
                "pack_dir": self.pack_dir,
                "memes_dir": self.pack_dir / "memes",
                "metadata_path": self.pack_dir / "memes_data.json",
                "manifest_path": self.pack_dir / "manifest.json",
            }
        try:
            return get_active_pack_paths()
        except Exception:
            return {
                "memes_dir": Path(MEMES_DIR),
                "metadata_path": Path(MEMES_DATA_PATH),
                "manifest_path": Path(ACTIVE_PACK_MANIFEST_PATH),
            }

    def __init__(self, pack_dir: Path | str | None = None):
        self.pack_dir = Path(pack_dir).resolve() if pack_dir is not None else None
        """初始化类别管理器"""
        ensure_dir_exists(self._active_paths()["memes_dir"])
        self._ensure_data_file()
        self.descriptions = self._load_descriptions()
        try:
            self._repository().cleanup_stale_trash()
        except Exception as exc:
            logger.warning("清理临时回收目录失败: %s", exc)

    def _repository(self) -> PackRepository:
        return PackRepository(Path(self._active_paths()["pack_dir"]).resolve())

    def _ensure_data_file(self) -> None:
        """确保 memes_data.json 文件存在，不存在时基于当前包内容初始化。"""
        paths = self._active_paths()
        if not paths["metadata_path"].exists():
            initial_descriptions = self._build_initial_descriptions()
            save_json(initial_descriptions, str(paths["metadata_path"]))
            logger.info(f"初始化类别描述文件: {paths['metadata_path']}")
            sync_pack_metadata(paths["pack_dir"], initial_descriptions)

    def _build_initial_descriptions(self) -> dict[str, str]:
        """在缺失 memes_data.json 时，从目录与 manifest 构建初始描述。"""
        descriptions: dict[str, str] = {}
        local_categories = self.get_local_categories()

        # 1) 优先读取当前包 manifest 的分类描述（官方包通常只带 manifest）
        try:
            manifest_path = self._active_paths()["manifest_path"]
            if manifest_path.is_file():
                with manifest_path.open(encoding="utf-8-sig") as file_obj:
                    manifest = json.load(file_obj)
                categories = (
                    manifest.get("categories", {}) if isinstance(manifest, dict) else {}
                )
                if isinstance(categories, dict):
                    for category, meta in categories.items():
                        key = str(category or "").strip()
                        if not key or key not in local_categories:
                            continue
                        if isinstance(meta, dict):
                            descriptions[key] = str(
                                meta.get("description") or "请添加描述"
                            )
                        else:
                            descriptions[key] = str(meta or "请添加描述")
        except Exception as exc:
            logger.warning(f"从 manifest 初始化类别描述失败: {exc}")

        # 2) 补齐实际目录存在但 manifest 未声明的分类
        for category in local_categories:
            descriptions.setdefault(category, "请添加描述")

        return descriptions

    def _load_descriptions(self) -> dict[str, str]:
        """加载类别描述配置"""
        metadata_path = self._active_paths()["metadata_path"]
        if not metadata_path.exists():
            self._ensure_data_file()
        return load_json(str(metadata_path), {})

    def reload_descriptions(self) -> dict[str, str]:
        """Reload category descriptions from disk."""
        self.descriptions = self._load_descriptions()
        return self.descriptions

    def _invalidate_semantic_if_present(self) -> None:
        pack_dir = Path(self._active_paths()["pack_dir"]).resolve()
        if not (pack_dir / "semantic_metadata.json").is_file():
            return
        try:
            invalidate_semantic_metadata(pack_dir)
        except Exception as exc:
            logger.error(f"分类变更后刷新语义元数据失败: {exc}", exc_info=True)

    def get_local_categories(self) -> set[str]:
        try:
            store = MemeStore(Path(self._active_paths()["memes_dir"]).resolve().parent)
            store.reindex_flat_catalog()
            return {
                tag
                for item in store.load_catalog().get("items", [])
                if isinstance(item, dict)
                for tag in item.get("tags", [])
                if canonical_tag(tag)
            }
        except Exception as exc:
            logger.error("unable to read virtual meme tags: %s", exc)
            return set()
    def get_sync_status(self) -> tuple[list[str], list[str]]:
        """获取同步状态
        返回: (missing_in_config, deleted_categories)
        """
        local_categories = self.get_local_categories()
        self.reload_descriptions()
        config_categories = set(self.descriptions.keys())

        return (
            list(local_categories - config_categories),  # 本地有但配置没有
            list(config_categories - local_categories),  # 配置有但本地没有
        )

    def update_description(self, category: str, description: str) -> bool:
        """更新类别描述"""
        try:
            category = str(category or "").strip()
            if not is_safe_category_name(category):
                return False
            self.reload_descriptions()
            old_description = str(self.descriptions.get(category) or "")
            self.descriptions[category] = description  # 更新内存中的 descriptions
            metadata_path = self._active_paths()["metadata_path"]
            saved = save_json(self.descriptions, str(metadata_path))
            if saved:
                pack_dir = Path(self._active_paths()["pack_dir"])
                sync_pack_metadata(pack_dir, self.descriptions)
                _reconcile_pack_catalogs(pack_dir)
                if " ".join(old_description.split()) != " ".join(
                    str(description).split()
                ):
                    self._invalidate_semantic_if_present()
            return saved
        except Exception as e:
            logger.error(f"更新类别描述失败: {e}")
            return False

    def remove_from_config(self, category: str) -> bool:
        """Remove a category from the description config only (keep directory on disk)."""
        try:
            category = str(category or "").strip()
            if not is_safe_category_name(category):
                return False
            self.reload_descriptions()
            if category not in self.descriptions:
                return False
            del self.descriptions[category]
            saved = save_json(
                self.descriptions, str(self._active_paths()["metadata_path"])
            )
            if saved:
                pack_dir = Path(self._active_paths()["pack_dir"])
                sync_pack_metadata(pack_dir, self.descriptions)
                _reconcile_pack_catalogs(pack_dir)
                self._invalidate_semantic_if_present()
            return saved
        except Exception as e:
            logger.error(f"从配置中移除类别失败: {e}")
            return False

    def get_descriptions(self) -> dict[str, str]:
        """获取所有类别描述"""
        self.reload_descriptions()
        return {
            canonical_tag(key) or key: value
            for key, value in self.descriptions.items()
        }

    def sync_with_filesystem(self) -> bool:
        """同步文件系统和配置：将配置强制对齐为实际文件夹结构"""
        try:
            self.reload_descriptions()
            local_categories = self.get_local_categories()
            changed = False

            # 为新类别添加默认描述
            for category in local_categories:
                if category not in self.descriptions:
                    self.descriptions[category] = "请添加描述"
                    changed = True

            # 删除配置中不存在对应文件夹的条目
            stale = [c for c in list(self.descriptions) if c not in local_categories]
            for category in stale:
                del self.descriptions[category]
                changed = True

            if changed:
                saved = save_json(
                    self.descriptions, str(self._active_paths()["metadata_path"])
                )
                if saved:
                    pack_dir = Path(self._active_paths()["pack_dir"])
                    sync_pack_metadata(pack_dir, self.descriptions)
                    _reconcile_pack_catalogs(pack_dir)
                    self._invalidate_semantic_if_present()
                return saved
            pack_dir = Path(self._active_paths()["pack_dir"])
            sync_pack_metadata(pack_dir, self.descriptions)
            _reconcile_pack_catalogs(pack_dir)
            return True
        except Exception as e:
            logger.error(f"同步文件系统失败: {e}")
            return False
