# 移除表情包管理页面与死接口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除表情包管理 WebUI 页面、其专属前端资源、只被它使用的后端 Web API,并删除顶层旧版页面副本,入口改为直接进入表情索引。

**Architecture:** 前端只保留 `pages/a_manage/{semantic,settings,catalog}` 三套自包含页面;后端路由表 `mixins/web_routes.py` 删除死路由,`mixins/emoji_api.py` 与 `mixins/pack_api.py` 删除对应 handler 并清理 import;底层后端函数与聊天命令保留。测试先声明新契约(被删路由/页面引用必须不存在),再删代码使其通过。

**Tech Stack:** Python unittest、HTML/CSS/JavaScript、AstrBot plugin page 机制、`node --check`。

## Global Constraints

- 版本号统一升级为 `v2.2.0`(`metadata.yaml` 与 `main.py` 注册版本一致)。
- 保留共享 Web 路由:`packs`、`packs/<pack_id>`、`packs/export*`、`packs/import*`、`meme_image_data`、`capture/*`、`settings/*`、`community/index/*`、`community/install`。
- 保留底层函数:`backend/models.py` 的 `add_emoji_to_category`/`scan_emoji_folder` 等、`backend/pack_storage.py` 的 `set_default_pack`/`uninstall_pack`、`install_official_first` 服务与聊天命令。
- 不修改剩余页面(表情索引/设置中心/资源广场)的布局、样式与交互逻辑,只改导航。
- 验证门禁:全量 unittest、compileall、schema 检查、架构检查、全部 JS `node --check`、`git diff --check`、SELF_CHECK_WORKFLOW 缺失 self/已删符号/路由一致性检查。

---

### Task 1: 路由契约测试先行

**Files:**
- Modify: `tests/test_web_route_capabilities.py`

**Interfaces:**
- Consumes: `mixins.web_routes.enabled_route_specs(capabilities)`
- Produces: 被删路由不注册的回归断言

- [ ] **Step 1: 更新 `test_default_surface_registers_ordinary_catalog_routes`**
  期望路由去掉 `emoji`、`emotions`,保留 `packs`、`packs/import`、`settings/rules`、`capture/workspace` 等,并加入 `meme_image_data`、`packs/export/status`。
- [ ] **Step 2: 更新 `test_core_routes_always_registered`**
  期望路由改为 `("packs", "packs/<pack_id>", "settings/rules", "meme_image_data")`。
- [ ] **Step 3: 新增 `test_removed_manage_routes_are_not_registered`**
  对 `DEFAULT_CAPABILITIES` 与 `{"core"}` 表面断言以下 path 均不存在:`emoji`、`emoji/<category>`、`emoji/add/<category>`、`emoji/delete`、`emoji/batch_delete`、`emoji/move`、`emoji/batch_move`、`emoji/batch_copy`、`emoji/clear_all`、`emotions`、`category/delete`、`category/clear`、`category/restore`、`category/rename`、`category/update_description`、`category/remove_from_config`、`sync/status`、`sync/config`、`meme_image`、`packs/default`、`packs/uninstall`、`community/install_official_first`。
- [ ] **Step 4: 运行该测试文件,确认新断言在当前代码上失败**

```powershell
python -m unittest tests.test_web_route_capabilities -v
```

Expected: 新增的 `test_removed_manage_routes_are_not_registered` FAIL。

### Task 2: 页面与前端资产测试收敛

**Files:**
- Modify: `tests/test_capture_index_page.py`
- Modify: `tests/test_webui_navigation_auth.py`
- Modify: `tests/test_semantic_removal.py`
- Modify: `tests/test_pack_local_management.py`
- Delete: `tests/test_image_preview_ui.py`

**Interfaces:**
- Consumes: `pages/a_manage/semantic/`、`pages/a_manage/settings/`、`pages/a_manage/catalog/` 现有文件
- Produces: 剩余页面导航契约断言

- [ ] **Step 1: `test_capture_index_page.py`**
  将所有 `for page_dir in (ROOT / "pages" / "semantic", ROOT / "pages" / "a_manage" / "semantic")` 循环收敛为只使用 `ROOT / "pages" / "a_manage" / "semantic"`;同步调整依赖双副本的断言(如缓存版本一致)。
- [ ] **Step 2: `test_webui_navigation_auth.py`**
  - 删除依赖 `api.js`、`pack.js`、`a_manage/index.html` 的用例:`test_a_manage_navigation_runtime_stays_inside_sandbox`、`test_first_use_catalog_guide_reuses_rewritten_catalog_link`、`test_pack_switch_refreshes_in_frame_navigation_params`。
  - `test_a_manage_page_links_use_in_frame_relative_paths`:文件列表改为三个剩余页面,并断言 `data-nav-page="a_manage"` 与 `/#/plugin-page/` 均不出现。
  - `test_nested_page_assets_are_copied_into_the_a_manage_scope`:页面列表收敛为 `("semantic", "settings", "catalog")`。
  - `test_entry_redirect_does_not_copy_static_asset_token`:重定向目标改为 `/#/plugin-page/meme_manager_master/a_manage/semantic`。
  - `test_capture_index_links_stay_inside_a_manage_page`:改为断言 semantic 页只有 settings/catalog 两个导航链接且无 a_manage。
  - `test_settings_assets_have_cache_busters_in_both_page_copies` 与 `test_a_manage_navigation_scripts_have_fresh_cache_busters`:去掉双副本与 `a_manage/index.html`/`api.js` 项。
- [ ] **Step 3: `test_semantic_removal.py`**
  删除读取 `a_manage/index.html`、`emoji.js`、`pack.js`、`script.js` 的四个用例(`test_manage_page_has_no_semantic_controls`、`test_manage_page_has_no_stale_semantic_preview_markup`、`test_manage_scripts_do_not_call_semantic_endpoints`、`test_manage_scripts_have_no_removed_semantic_placeholders`),其余语义移除断言保留。
- [ ] **Step 4: `test_pack_local_management.py`**
  删除直接调用 `_api_delete_emoji`、`_api_add_emoji`、`_api_batch_move_emojis`、`_api_clear_category` 的用例;将「删除保留 manifest/catalog 一致」断言迁移为直接调用 `backend.models.delete_emoji_from_category` 的测试;保留 `test_category_manager_can_update_selected_pack_metadata`。删除 `test_fixed_tag_ui_no_longer_calls_retired_category_mutations`(被删前端文件)。
- [ ] **Step 5: 删除 `tests/test_image_preview_ui.py`**(只测被删管理页预览弹窗)。
- [ ] **Step 6: 运行相关测试,确认更新后的断言在当前代码上失败**

### Task 3: 后端路由表删除

**Files:**
- Modify: `mixins/web_routes.py`

**Interfaces:**
- Consumes: 现有 `ROUTES` 元组
- Produces: 删除 22 条管理页专属路由后的 `ROUTES`

- [ ] **Step 1: 从 `ROUTES` 删除以下 WebRouteSpec**
  `emoji`、`emoji/<category>`、`emoji/add/<category>`、`emoji/delete`、`emoji/batch_delete`、`emoji/move`、`emoji/batch_move`、`emoji/batch_copy`、`emoji/clear_all`、`emotions`、`category/delete`、`category/clear`、`category/restore`、`category/rename`、`category/update_description`、`category/remove_from_config`、`sync/status`、`sync/config`、`meme_image`、`packs/default`、`packs/uninstall`、`community/install_official_first`。
- [ ] **Step 2: 运行 Task 1 路由测试,确认通过**

### Task 4: mixin handler 删除与 import 清理

**Files:**
- Modify: `mixins/emoji_api.py`
- Modify: `mixins/pack_api.py`

**Interfaces:**
- Consumes: `mixins/web_routes.py` 删除后的路由表
- Produces: `EmojiAPIMixin` 只保留 `_api_get_meme_image_data`;`PackAPIMixin` 删除 `_api_set_default_pack`、`_api_uninstall_pack`、`_api_install_official_first_pack`

- [ ] **Step 1: `mixins/emoji_api.py`**
  删除 `_api_get_emojis`、`_api_get_emoji_by_category`、`_api_add_emoji`、`_api_delete_emoji`、`_api_batch_delete_emojis`、`_api_move_emoji`、`_api_batch_move_emojis`、`_api_batch_copy_emojis`、`_api_clear_all_emojis`、`_api_get_emotions`、`_api_delete_category`、`_api_clear_category`、`_api_restore_category`、`_api_rename_category`、`_api_update_description`、`_api_remove_from_config`、`_api_sync_status`、`_api_sync_config`、`_api_serve_meme_image`;只保留 `_api_get_meme_image_data`。
- [ ] **Step 2: 清理 `mixins/emoji_api.py` 中不再使用的 import**
  用仓库搜索确认 `add_emoji_to_category`、`scan_emoji_folder`、`set_default_pack`、`uninstall_pack` 等在本文件是否仍被引用;`_api_get_meme_image_data` 需要保留的依赖(如 `image_preview_mode`、`MemeStore`、`is_safe_category_segment`、PIL/quart)逐一确认。
- [ ] **Step 3: `mixins/pack_api.py`**
  删除 `_api_set_default_pack`、`_api_uninstall_pack`、`_api_install_official_first_pack`,并清理因此不再使用的 import;注意 `_api_import_pack`/`_api_apply_pack_import` 等仍保留的路由可能依赖 `set_default_pack`,搜索确认后再删。
- [ ] **Step 4: 运行 `python -m unittest tests.test_web_route_capabilities tests.test_web_api_behavior tests.test_capture_index_api tests.test_pack_local_management -v`**
  处理遗留的 AttributeError/import 错误,直到通过;同时运行 `python -m compileall -q .`。
- [ ] **Step 5: 运行 `docs/SELF_CHECK_WORKFLOW.md` 第 3-5 节的 AST 脚本**
  确认无缺失 self、无残留调用已删符号、路由-处理器一致。

### Task 5: 前端删除与导航更新

**Files:**
- Delete: `pages/a_manage/index.html`、`api.js`、`state.js`、`dialogs.js`、`emoji.js`、`pack.js`、`script.js`、`style.css`、`fa.min.css`、`webfonts/`
- Delete: `pages/semantic/`、`pages/settings/`、`pages/catalog/`
- Modify: `pages/index.html`
- Modify: `pages/a_manage/semantic/index.html`
- Modify: `pages/a_manage/settings/index.html`
- Modify: `pages/a_manage/catalog/index.html`
- Modify: `pages/a_manage/semantic/script.js`、`pages/a_manage/settings/script.js`、`pages/a_manage/catalog/script.js`

**Interfaces:**
- Consumes: Task 2 的页面契约断言
- Produces: 剩余三页无 a_manage 引用的导航

- [ ] **Step 1: 删除管理页专属文件与顶层旧版副本目录**
  (使用 `Remove-Item -Recurse -Force -LiteralPath`,先解析确认目标在 `pages/` 内。)
- [ ] **Step 2: `pages/index.html`**
  重定向改为 `window.location.replace("/#/plugin-page/meme_manager_master/a_manage/semantic")`。
- [ ] **Step 3: `pages/a_manage/semantic/index.html`**
  移除 `<a href="../index.html" data-nav-page="a_manage">返回表情管理</a>`。
- [ ] **Step 4: `pages/a_manage/settings/index.html` 与 `pages/a_manage/catalog/index.html`**
  移除 `href="../index.html" data-nav-page="a_manage"` 的中心返回链接,保留左右导航。
- [ ] **Step 5: 三个脚本**
  导航白名单改为 `new Set(["catalog", "settings", "semantic"])`。
- [ ] **Step 6: 缓存版本 bump**
  内容变化的 `semantic/index.html`、`settings/index.html`、`catalog/index.html` 及其脚本/style 引用改为 `20260817-remove-manage-1`。
- [ ] **Step 7: 运行 `node --check` 检查剩余全部 JS,并运行 Task 2 页面测试**

### Task 6: 文档与版本

**Files:**
- Modify: `README.md`、`CHANGELOG.md`、`metadata.yaml`、`main.py`
- Modify: `docs/ARCHITECTURE.md`、`docs/CONFIGURATION.md`(仅当包含被删页面/接口描述)
- Modify: `plan.md`、`task_plan.md`、`progress.md`、`findings.md`

**Interfaces:**
- Produces: v2.2.0 版本与发布记录

- [ ] **Step 1: `README.md`**
  WebUI 段落改为「入口即表情索引」;同步「主要能力」中依赖管理页的措辞;验证命令中 JS 检查改为 `Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }`。
- [ ] **Step 2: `CHANGELOG.md`**
  新增 `## [v2.2.0] - 2026-08-17`,记录移除页面/路由/旧副本、入口变更、验证结果。
- [ ] **Step 3: `metadata.yaml` 与 `main.py`**
  版本统一改为 `v2.2.0`。
- [ ] **Step 4: 工作记录**
  更新 `plan.md`(勾选/新计划)、`task_plan.md`、`progress.md`、`findings.md`。

### Task 7: 全量验证

**Files:**
- None (验证)

- [ ] **Step 1: 运行完整验证门禁**

```powershell
python -m unittest discover -s tests
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
git diff --check
```

- [ ] **Step 2: 运行 SELF_CHECK_WORKFLOW 的缺失 self / 已删符号 / 路由-处理器检查脚本**
- [ ] **Step 3: 复查 `git diff`,确认无残留引用、调试输出或敏感信息**
