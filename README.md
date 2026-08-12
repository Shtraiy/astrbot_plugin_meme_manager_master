<div align="center">

# 表情包管理大师

[![version](https://img.shields.io/badge/version-v2.1.4-blue.svg)](https://github.com/Shtraiy/astrbot_plugin_meme_manager_master)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.5.7-orange.svg)](https://github.com/Soulter/AstrBot)

**让表情包管理、收集与选图更简单**
</div>

> **meme_manager_master** 是一个参考 AstrBot 原版 `meme_manager` 重构、拥有独立运行空间的表情包管理插件，保留了群聊图片自动识别、分类和收集能力，并提供 AstrBot 内置 WebUI。

> [!NOTE]
> 本插件使用独立的数据目录与 WebUI API 路由，可以与原版 `meme_manager` 插件并存；详细迁移规则见[数据结构](#-数据结构)。

## 📌 主要能力

- 在 AstrBot WebUI 的插件页面直接打开“表情包管理大师”。
- 按分类浏览、上传、删除、移动和批量管理图片。
- 捕获索引工作台支持已整理与待处理表情的统一批量处置：已整理项删除并拉黑，普通待分类项忽略、删除并拉黑，重复项忽略并拉黑但保留已有图片。
- 手动忽略或从索引工作台删除的图片会写入插件级精确 SHA-256 永久黑名单；后续自动收集会在识图前和保存前拦截，所有资源包共享。
- 使用 pack 运行时保存表情包，支持默认包、导入导出和会话/人格选包规则。
- 参考原版 `meme_manager` 的分类标记、语义候选和精确 ID 选图逻辑。
- 自动识别群聊图片，使用视觉模型判断是否为表情包，再按场景分类保存。
- 机器人回复完成后由情景模型统一判断是否追加本地表情包；其他插件生成的图片、文件、视频或音频不会被本插件抢占或再次追加表情包。
- 支持 `/偷取`、`/表情管理` 命令组和 `/表情偷取状态` 状态检查。

## 🖥️ WebUI

安装并启用插件后，在 AstrBot WebUI 的“插件”页面打开“表情包管理大师”。页面由插件 `pages/` 目录提供，后端 API 使用 AstrBot 的 `context.register_web_api` 注册，不需要额外端口。

管理页面支持分类浏览、图片上传、图片预览、删除、移动、分类描述编辑和 pack 切换；表情索引页在已整理区与待处理区之间提供独立分页，并支持跨已整理分页累积选择。普通管理页的删除行为不写入捕获黑名单。图片选择使用现有的情景判断和分类规则，不再生成或维护图片语义描述、向量索引或语义复审任务。

## 📦 数据结构

运行时数据位于：

```text
AstrBot/data/plugin_data/meme_manager_master/
├── capture_blacklist.json
└── packs/
    └── <pack_id>/
        ├── manifest.json
        ├── memes_data.json
        └── memes/<category>/
            └── index.json
```

`capture_blacklist.json` 是插件级全局数据，不随单个资源包导入、导出或卸载；全量运行时备份会包含它，恢复时与当前黑名单取并集。

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

WebUI 管理页脚本按依赖顺序拆分为 `state.js`、`api.js`、`dialogs.js`、
`pack.js`、`emoji.js` 与入口 `script.js`，共享命名空间
`window.MemeManagerUI`；本地用 `node --check pages/a_manage/*.js` 做语法
检查，页面交互仍需在 AstrBot WebUI 中手动验证。
