<div align="center">

# 表情包管理大师

[![version](https://img.shields.io/badge/version-v2.4.0-blue.svg)](https://github.com/Shtraiy/astrbot_plugin_meme_manager_master)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.5.7-orange.svg)](https://github.com/Soulter/AstrBot)

**让表情包管理、收集与选图更简单**
</div>

> **meme_manager_master** 是一个参考 AstrBot 原版 `meme_manager` 重构、拥有独立运行空间的表情包管理插件，保留了群聊图片自动识别、分类和收集能力，并提供 AstrBot 内置 WebUI。

> [!NOTE]
> 本插件使用独立的数据目录与 WebUI API 路由，可以与原版 `meme_manager` 插件并存；详细迁移规则见[数据结构](#-数据结构)。

## 📌 主要能力

- 在 AstrBot WebUI 的插件页面直接打开“表情包管理大师”，入口即表情索引工作台。
- 表情索引工作台按分类浏览缩略图、处置捕获图片、维护 v4 语义索引，并支持表情包导出与导入；手动上传、删除、移动与分类维护通过聊天命令完成。
- 捕获索引工作台支持已整理与待处理表情的统一批量处置：已整理项删除并拉黑，普通待分类项忽略、删除并拉黑；重复图片会自动进入临时黑名单，不再生成待分类记录，并保留已有图片。
- 手动忽略或从索引工作台删除的图片会写入插件级精确 SHA-256 永久黑名单；自动重复黑名单会记录来源资源包和文件名，原图被删除后自动移除。两类黑名单都会在识图前和保存前拦截，所有资源包共享。
- 使用 pack 运行时保存表情包，支持默认包、导入导出和会话/人格选包规则。
- 采用 12 个稳定主分类路由，辅助语义最多保留 2 个，并用精确 ID 选图。
- 索引会整理图片描述、可见配字、文字含义、适用场景和避免场景，降低带字表情包误用。
- 表情索引页的“全量语义重索引”会扫描整个资源包、整理旧目录；已有完整 v4 索引会跳过视觉模型，旧版或字段不完整的图片会重新识别，并写入 `full_reindex_status` 检查标记。
- 表情索引工作台提供 v4 健康面板；可按“v4 完整、需重建、待分类”气泡筛选当前资源包，重复记录会在整理时自动归入黑名单。
- 全量语义重索引按批次保存检查点并持久化进度；切换 WebUI 页面、插件重载或任务中断后，重新打开页面会自动恢复，已完成图片不会重复调用模型。
- 自动识别群聊图片，使用视觉模型判断是否为表情包，再按场景分类保存。
- 机器人回复完成后由情景模型统一判断是否追加本地表情包；其他插件生成的图片、文件、视频或音频不会被本插件抢占或再次追加表情包。
- 支持 `/偷取`、`/表情管理` 命令组和 `/表情偷取状态` 状态检查。

## 🖥️ WebUI

安装并启用插件后，在 AstrBot WebUI 的“插件”页面打开“表情包管理大师”，直接进入表情索引工作台。页面由插件 `pages/` 目录提供，后端 API 使用 AstrBot 的 `context.register_web_api` 注册，不需要额外端口。

表情索引页提供 v4 健康面板、状态气泡筛选、已整理区独立分页和跨页累积选择，支持删除并拉黑、忽略、批量处置与全量语义重索引；工具栏支持导出当前资源包（分享版或带向量自用备份）和导入表情包（含预检与设为默认选项）。手动上传、分类改名/描述编辑、默认包切换等操作由聊天命令提供。自动选图只按主分类建立候选集合，图片语义字段仅用于模型判断；旧目录无法无歧义推断主分类时会标记为 `needs_reindex`，需要点击“全量语义重索引”完成语义重建后才会进入自动发送候选。

## 📦 数据结构

运行时数据位于：

```text
AstrBot/data/plugin_data/meme_manager_master/
├── capture_blacklist.json
├── capture_auto_blacklist.json
└── packs/
    └── <pack_id>/
        ├── manifest.json
        ├── memes_data.json
        └── memes/<category>/
            └── index.json
```

`capture_blacklist.json` 是插件级全局手动黑名单，不随单个资源包导入、导出或卸载；自动重复黑名单保存在同目录的 `capture_auto_blacklist.json`，由来源文件是否仍存在决定是否保留。

本插件只迁移自己的旧版 `meme_manager_master/memes/` 和 `memes_data.json` 到 `legacy-migrated` pack，不会读取或覆盖原版 `meme_manager` 的数据。本插件的自动收集会跟随当前默认 pack，避免与 WebUI 管理目录分离。

首次启动时，如果检测到原版 `plugin_data/meme_manager/`，会把其中的全部 pack、`memes_data.json`、分类目录、`index.json`、语义元数据、向量索引和选择规则增量导入到本插件目录。也支持把旧版 `memes/` 直接复制到本插件数据目录，启动时会自动迁移为 `legacy-migrated` pack。

本插件的内部 ID 是 `meme_manager_master`，管理命令组是 `/表情管理大师`；原版插件的 `meme_manager` 和 `/表情管理` 可以保留，两者不会共用数据目录或 WebUI API 路由。

## ⚙️ 配置

Web 设置只保留识图模型、情景判断模型、自动收集开关、群组白名单和自动发送控制等日常选项。高级运行参数仍由 `runtime_config.PluginConfig` 兼容读取，但不再全部暴露在 AstrBot Web 界面；详细说明见 `CONFIGURATION.md`。`_conf_schema.json` 由 `scripts/generate_conf_schema.py` 生成，可用 `python scripts/generate_conf_schema.py --check` 检查同步状态。

## 🧰 可选依赖

核心安装只需要 `requirements.txt` 中的 `aiohttp`、`Pillow` 与 `requests`。图片会发送给配置的视觉/情感模型进行情景判断，请确认群成员已知悉并遵守平台、隐私和内容管理要求。

## ✅ 开发与验证

每次修改后运行完整验证门禁：

```text
python -m unittest discover -s tests -v
python -m compileall -q .
python scripts/generate_conf_schema.py --check
git diff --check
```

WebUI 由 `pages/a_manage/` 下的表情索引页面（入口跳转页指向它）组成；本地对所有
页面脚本运行 `node --check` 做语法检查，页面交互仍需在 AstrBot WebUI 中手动验证。
