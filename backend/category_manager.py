import json
import logging
import os
import shutil
from pathlib import Path

from ..config import (
    ACTIVE_PACK_MANIFEST_PATH,
    MEMES_DATA_PATH,
    MEMES_DIR,
    sync_active_pack_metadata,
    get_active_pack_paths,
)
from ..utils import ensure_dir_exists, load_json, save_json
from ..storage import MemeStore, is_safe_category_segment
from .semantic_storage import invalidate_semantic_metadata

logger = logging.getLogger(__name__)


def _reconcile_active_catalogs() -> None:
    """Keep the active pack's per-category JSON/README indexes in sync."""
    try:
        MemeStore(Path(get_active_pack_paths()["pack_dir"]).resolve()).reconcile_catalogs()
    except Exception as exc:
        logger.warning("同步分类索引失败: %s", exc, exc_info=True)


def is_safe_category_name(category: str) -> bool:
    """Return whether category stays within one memes directory segment."""
    return is_safe_category_segment(category)


class CategoryManager:
    @staticmethod
    def _active_paths() -> dict[str, Path | str]:
        try:
            return get_active_pack_paths()
        except Exception:
            return {
                "memes_dir": Path(MEMES_DIR),
                "metadata_path": Path(MEMES_DATA_PATH),
                "manifest_path": Path(ACTIVE_PACK_MANIFEST_PATH),
            }

    def __init__(self):
        """初始化类别管理器"""
        ensure_dir_exists(self._active_paths()["memes_dir"])
        self._ensure_data_file()
        self.descriptions = self._load_descriptions()

    def _ensure_data_file(self) -> None:
        """确保 memes_data.json 文件存在，不存在时基于当前包内容初始化。"""
        paths = self._active_paths()
        if not paths["metadata_path"].exists():
            initial_descriptions = self._build_initial_descriptions()
            save_json(initial_descriptions, str(paths["metadata_path"]))
            logger.info(f"初始化类别描述文件: {paths['metadata_path']}")
            sync_active_pack_metadata(initial_descriptions)

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
        """获取本地文件夹中的类别"""
        try:
            memes_dir = self._active_paths()["memes_dir"]
            ensure_dir_exists(memes_dir)
            return {
                d
                for d in os.listdir(memes_dir)
                if os.path.isdir(os.path.join(memes_dir, d))
            }
        except Exception as e:
            logger.error(f"获取本地类别失败: {e}")
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
                sync_active_pack_metadata(self.descriptions)
                _reconcile_active_catalogs()
                if " ".join(old_description.split()) != " ".join(
                    str(description).split()
                ):
                    self._invalidate_semantic_if_present()
            return saved
        except Exception as e:
            logger.error(f"更新类别描述失败: {e}")
            return False

    def create_category(self, category: str, description: str = "请添加描述") -> bool:
        """创建类别目录并写入描述。"""
        try:
            category = category.strip()
            description = description.strip() or "请添加描述"
            if not is_safe_category_name(category):
                return False

            memes_dir = self._active_paths()["memes_dir"]
            os.makedirs(os.path.join(memes_dir, category), exist_ok=True)
            saved = self.update_description(category, description)
            if saved:
                _reconcile_active_catalogs()
            return saved
        except Exception as e:
            logger.error(f"创建类别失败: {e}")
            return False

    def rename_category(self, old_name: str, new_name: str) -> bool:
        """重命名类别"""
        try:
            self.reload_descriptions()
            old_name = str(old_name or "").strip()
            new_name = str(new_name or "").strip()
            if (
                not is_safe_category_name(old_name)
                or old_name not in self.descriptions
                or not is_safe_category_name(new_name)
                or (new_name != old_name and new_name in self.descriptions)
            ):
                return False

            memes_dir = self._active_paths()["memes_dir"]
            old_path = memes_dir / old_name
            new_path = memes_dir / new_name
            if new_name != old_name and new_path.exists():
                return False

            # 获取旧类别的描述
            description = self.descriptions[old_name]

            # 更新配置
            del self.descriptions[old_name]
            self.descriptions[new_name] = description

            # 更新文件夹名称
            if os.path.exists(old_path):
                os.rename(old_path, new_path)

            metadata_path = self._active_paths()["metadata_path"]
            saved = save_json(self.descriptions, str(metadata_path))
            if saved:
                sync_active_pack_metadata(self.descriptions)
                _reconcile_active_catalogs()
                self._invalidate_semantic_if_present()
            return saved
        except Exception as e:
            logger.error(f"重命名类别失败: {e}")
            return False

    def delete_category(self, category: str) -> bool:
        """删除类别"""
        try:
            category = str(category or "").strip()
            if not is_safe_category_name(category):
                return False
            self.reload_descriptions()
            # 从配置中删除
            if category in self.descriptions:
                del self.descriptions[category]
                save_json(self.descriptions, str(self._active_paths()["metadata_path"]))

            # 删除文件夹
            category_path = os.path.join(self._active_paths()["memes_dir"], category)
            if os.path.exists(category_path):
                shutil.rmtree(category_path)

            sync_active_pack_metadata(self.descriptions)
            _reconcile_active_catalogs()
            self._invalidate_semantic_if_present()
            return True
        except Exception as e:
            logger.error(f"删除类别失败: {e}")
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
                sync_active_pack_metadata(self.descriptions)
                _reconcile_active_catalogs()
                self._invalidate_semantic_if_present()
            return saved
        except Exception as e:
            logger.error(f"从配置中移除类别失败: {e}")
            return False

    def get_descriptions(self) -> dict[str, str]:
        """获取所有类别描述"""
        self.reload_descriptions()
        return self.descriptions.copy()  # 返回字典的副本

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
                    sync_active_pack_metadata(self.descriptions)
                    _reconcile_active_catalogs()
                    self._invalidate_semantic_if_present()
                return saved
            sync_active_pack_metadata(self.descriptions)
            _reconcile_active_catalogs()
            return True
        except Exception as e:
            logger.error(f"同步文件系统失败: {e}")
            return False
