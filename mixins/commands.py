import os
import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.all import *
from astrbot.api.event import AstrMessageEvent, filter

from ..backend.models import (
    clear_all_emojis,
    clear_category_emojis,
    get_emoji_by_category,
)
from ..backend.pack_storage import install_first_official_pack_from_index
from ..config import COMMUNITY_INDEX_URL
from ..backend.tagging import canonical_tag
from ..storage import MemeStore


class CommandMixin:
    """表情包管理命令组及所有管理命令"""

    def _assert_default_pack_mutation_allowed(self, operation: str) -> str:
        pack_id = str(self._default_pack_context()["pack_id"] or "").strip()
        if pack_id:
            self.catalog_index_service.assert_pack_mutation_allowed(pack_id, operation)
        return pack_id

    @filter.command_group("表情管理大师")
    def meme_manager_master(self):
        """表情包管理命令组:
        查看图库
        添加表情
        恢复默认表情包
        清空指定类型
        清空全部
        删除类型本身
        图库统计
        """
        pass

    # ---------- 辅助方法 ----------
    async def _wait_for_command_confirmation(
        self, event: AstrMessageEvent, timeout: int = 30
    ) -> bool:
        @session_waiter(timeout=timeout, record_history_chains=False)
        async def confirmation_waiter(
            controller, confirm_event: AstrMessageEvent
        ) -> None:
            reply = (confirm_event.message_str or "").strip()
            if reply in {"确认", "确定"}:
                controller.stop()
                return
            if reply in {"取消", "退出"}:
                await confirm_event.send(confirm_event.plain_result("已取消本次操作。"))
                controller.stop(ConfirmationCancelled())
                return
            await confirm_event.send(
                confirm_event.plain_result(
                    "请回复“确认”继续执行，或回复“取消”终止本次操作。"
                )
            )
            controller.keep(timeout=timeout, reset_timeout=True)

        try:
            await confirmation_waiter(event, SenderScopedSessionFilter())
            return True
        except TimeoutError:
            await event.send(event.plain_result("⌛ 等待确认超时，操作已取消。"))
            return False
        except ConfirmationCancelled:
            return False

    def _format_category_counts(
        self, category_counts: dict[str, int], limit: int = 8
    ) -> str:
        non_empty_items = [
            (c, cnt) for c, cnt in sorted(category_counts.items()) if cnt > 0
        ]
        if not non_empty_items:
            return "无可删除的表情包文件。"
        lines = [f"- {c}: {cnt} 个" for c, cnt in non_empty_items[:limit]]
        if len(non_empty_items) > limit:
            lines.append(f"- 其余 {len(non_empty_items) - limit} 个类型已省略")
        return "\n".join(lines)

    # ---------- 命令实现 ----------
    @meme_manager_master.command("查看图库")
    async def list_emotions(self, event: AstrMessageEvent):
        pack_context = self._resolve_runtime_pack_context(event=event)
        descriptions = pack_context.get("category_mapping") or self.category_mapping
        categories = "\n".join(
            [f"- {tag}: {desc}" for tag, desc in descriptions.items()]
        )
        yield event.plain_result(f"🖼️ 当前图库：\n{categories}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager_master.command("添加表情")
    async def upload_meme(self, event: AstrMessageEvent, category: str = None):
        category = canonical_tag(category) if category else category
        if not category:
            yield event.plain_result(
                "📌 若要添加表情，请按照此格式操作：\n/表情管理 添加表情 [类别名称]\n（输入/查看图库 可获取类别列表）"
            )
            return
        if category not in self.category_manager.get_descriptions():
            yield event.plain_result(
                f"您输入的表情包类别「{category}」是无效的哦。\n可以使用/查看表情包来查看可用的类别。"
            )
            return
        user_key = f"{event.session_id}_{event.get_sender_id()}"
        self.upload_states[user_key] = {
            "category": category,
            "expire_time": time.time() + 30,
        }
        yield event.plain_result(
            f"请在30秒内发送要添加到【{category}】类别的图片（可发送多张图片）。"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager_master.command("恢复默认表情包")
    async def restore_default_memes_command(
        self, event: AstrMessageEvent, category: str = None
    ):
        """从社区索引安装首个官方表情包并设为默认。"""
        if category:
            yield event.plain_result(
                "ℹ️ 该命令已改为从官方仓库安装默认包，不再支持按类别恢复。"
            )

        try:
            service = getattr(self, "community_pack_service", None)
            install_operation = (
                service.install_official_first
                if service is not None
                else install_first_official_pack_from_index
            )
            result = await self._run_guarded_runtime_file_operation(
                "安装官方资源包",
                install_operation,
                index_url=COMMUNITY_INDEX_URL,
                overwrite=False,
                set_as_default=True,
            )
            selected_name = str(
                result.get("selected_pack_name")
                or result.get("name")
                or result.get("pack_id")
                or ""
            )
            selected_pack_id = str(
                result.get("pack_id") or result.get("selected_pack_id") or ""
            )
            self._reload_personas()
            yield event.plain_result(
                f"✅ 已从官方仓库安装默认表情包：{selected_name} ({selected_pack_id})。"
            )
        except FileExistsError:
            yield event.plain_result(
                "⚠️ 目标表情包已存在。请先在广场或管理页卸载同名包后重试。"
            )
        except RuntimeError as exc:
            yield event.plain_result(f"⚠️ {exc}")
        except Exception as exc:
            logger.error("从官方仓库安装默认表情包失败: %s", exc, exc_info=True)
            yield event.plain_result(f"❌ 安装默认表情包失败：{exc}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager_master.command("清空指定类型")
    async def clear_category_command(
        self, event: AstrMessageEvent, category: str = None
    ):
        """清空指定类型下的所有表情包，但保留类型本身。"""
        if not category:
            yield event.plain_result(
                "📌 若要清空指定类型，请按照此格式操作：\n/表情管理 清空指定类型 [类别名称]"
            )
            return

        category = category.strip()
        available_categories = self._get_manageable_categories()
        if category not in available_categories:
            yield event.plain_result(
                f"⚠️ 未找到类型「{category}」。\n可先使用 /表情管理 查看图库 查看当前类型。"
            )
            return

        emoji_count = len(get_emoji_by_category(category))
        if emoji_count == 0:
            yield event.plain_result(f"📭 类型「{category}」当前没有可清空的表情包。")
            return

        yield event.plain_result(
            f"⚠️ 即将清空类型「{category}」下的 {emoji_count} 个表情包，但会保留类型本身。\n"
            "请在 30 秒内回复“确认”继续执行，或回复“取消”终止本次操作。"
        )
        if not await self._wait_for_command_confirmation(event):
            return

        try:
            self._assert_default_pack_mutation_allowed("清空表情分类")
        except RuntimeError as exc:
            yield event.plain_result(f"⚠️ {exc}")
            return

        result = clear_category_emojis(category)
        deleted_count = len(result["deleted_files"])
        yield event.plain_result(
            f"✅ 已清空类型「{category}」，共删除 {deleted_count} 个表情包。"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager_master.command("清空全部")
    async def clear_all_emojis_command(self, event: AstrMessageEvent):
        """清空所有类型下的表情包，但保留类型和描述配置。"""
        available_categories = sorted(self._get_manageable_categories())
        category_counts = {
            category: len(get_emoji_by_category(category))
            for category in available_categories
        }
        total_count = sum(category_counts.values())

        if total_count == 0:
            yield event.plain_result("📭 当前没有可清空的表情包文件。")
            return

        category_count = sum(1 for count in category_counts.values() if count > 0)
        summary = self._format_category_counts(category_counts)
        yield event.plain_result(
            f"⚠️ 即将清空全部表情包，共 {total_count} 个文件，涉及 {category_count} 个类型。\n"
            "该操作会保留所有类型名称和描述配置。\n"
            f"{summary}\n"
            "请在 30 秒内回复“确认”继续执行，或回复“取消”终止本次操作。"
        )
        if not await self._wait_for_command_confirmation(event):
            return

        try:
            self._assert_default_pack_mutation_allowed("清空全部表情图片")
        except RuntimeError as exc:
            yield event.plain_result(f"⚠️ {exc}")
            return

        result = clear_all_emojis()
        deleted_total = sum(result["deleted_by_category"].values())
        yield event.plain_result(
            f"✅ 已清空全部表情包，共删除 {deleted_total} 个文件，类型配置已保留。"
        )

    @meme_manager_master.command("图库统计")
    async def show_library_stats(self, event: AstrMessageEvent):
        store = MemeStore(Path(self._default_pack_context()["pack_dir"]).resolve())
        store.reindex_flat_catalog()
        counts: dict[str, int] = {}
        for item in store.load_catalog().get("items", []):
            if isinstance(item, dict):
                for tag in item.get("tags", []):
                    counts[tag] = counts.get(tag, 0) + 1
        total = len(store.load_catalog().get("items", []))
        lines = ["表情包图书馆统计", "", f"本地文件总数: {total}", f"标签数: {len(counts)}", ""]
        lines.extend(f"- {tag}: {count}" for tag, count in sorted(counts.items()))
        yield event.plain_result("\n".join(lines))
        return
        """显示图库详细统计信息"""
        try:
            result = ["📊 表情包图库统计报告", "", "📁 本地图库统计:"]

            # 统计本地文件
            local_stats = {}
            local_total = 0

            local_memes_dir = str(self._default_pack_context()["memes_dir"])
            if os.path.exists(local_memes_dir):
                for category in os.listdir(local_memes_dir):
                    category_path = os.path.join(local_memes_dir, category)
                    if os.path.isdir(category_path):
                        files = [
                            f
                            for f in os.listdir(category_path)
                            if f.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))
                        ]
                        count = len(files)
                        local_stats[category] = count
                        local_total += count

            # 显示本地统计
            if local_stats:
                result.append(f"  • 总文件数: {local_total} 个")
                result.append(f"  • 分类数: {len(local_stats)} 个")
                result.append("")
                result.append("📂 本地分类详情:")
                for cat, count in sorted(
                    local_stats.items(), key=lambda x: x[1], reverse=True
                ):
                    result.append(f"  • {cat}: {count} 个")
            else:
                result.append("  • 本地图库为空")

            # 存储空间估算
            result.append("")
            result.append("💾 存储空间估算:")
            if local_total > 0:
                # 假设平均每个文件 500KB
                estimated_size = local_total * 500 / 1024  # 转换为MB
                result.append(f"  • 本地图库约: {estimated_size:.1f} MB")


            yield event.plain_result("\n".join(result))

        except Exception as e:
            logger.error(f"获取图库统计失败: {str(e)}")
            yield event.plain_result(f"获取图库统计失败: {str(e)}")
