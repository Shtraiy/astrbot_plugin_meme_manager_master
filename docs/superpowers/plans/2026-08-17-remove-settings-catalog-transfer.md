# 移除设置中心与资源广场,导出/导入移植到表情索引 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除设置中心与资源广场页面及其专用 Web API,把表情包导出/导入移植到表情索引页,版本升至 v2.3.0。

**Architecture:** 前端只保留 `pages/a_manage/index.html` 跳转页与 `pages/a_manage/semantic/`;表情索引工具栏新增导出/导入控制。后端 `mixins/web_routes.py` 删除 9 条路由,`mixins/pack_api.py` 删除对应 handler 与 helper,保留导出/导入/捕获共享接口。测试先声明新契约(红→绿)。

**Tech Stack:** Python unittest、HTML/CSS/JavaScript、AstrBot plugin page 机制、`node --check`。

## Global Constraints

- 版本统一为 v2.3.0(`metadata.yaml` 与 `main.py` 注册版本一致)。
- 保留 Web 路由:`packs`、`packs/<pack_id>`、`packs/export/status`、`packs/export/download`、`packs/import/stage`、`packs/import/apply`、`capture/*`、`meme_image_data`。
- 保留聊天命令 `/恢复默认表情包` 与底层社区/导入导出服务。
- AstrBot 页面发现入口链路不变:`pages/index.html` → `a_manage` → `./semantic/index.html`。
- 验证门禁:全量 unittest、compileall、schema、架构检查、全部 JS `node --check`、`git diff --check`、SELF_CHECK 路由一致性。

---

### Task 1: 路由与页面契约测试先行

**Files:**
- Modify: `tests/test_web_route_capabilities.py`
- Modify: `tests/test_web_api_behavior.py`
- Modify: `tests/test_webui_navigation_auth.py`
- Modify: `tests/test_semantic_removal.py`
- Modify: `tests/test_capture_index_page.py`

**Interfaces:**
- Consumes: 现有路由表与页面文件
- Produces: 被删路由/页面不存在的回归断言

- [ ] **Step 1: `test_web_route_capabilities.py`**
  `REMOVED_MANAGE_ROUTES` 增加 `packs/export`、`packs/import`、`community/index/fetch`、`community/index/cache`、`community/install`、`settings/rules`、`settings/targets`、`settings/backup/export`、`settings/backup/import`;保留路由断言增加 `packs/import/stage`、`packs/import/apply`、`packs/export/download`;`test_core_routes_always_registered` 用 `packs/export/status` 替换 `settings/rules`。
- [ ] **Step 2: `test_web_api_behavior.py`**
  删除 `test_community_routes_use_composition_root_service`、`test_runtime_backup_base64_decoder_enforces_archive_limit`、`test_export_result_does_not_expose_local_archive_path`;保留导入凭证/包操作/安全用例。
- [ ] **Step 3: `test_webui_navigation_auth.py`**
  `REMAINING_PAGE_DIRS` 收敛为 `("semantic",)`;删除 settings/catalog 页面相关断言;新增「语义页无 settings/catalog 链接」断言;缓存版本断言只保留语义页。
- [ ] **Step 4: `test_semantic_removal.py`**
  删除 `test_settings_scripts_have_no_unreachable_semantic_rebuild_logic`(设置页已删)。
- [ ] **Step 5: `test_capture_index_page.py`**
  新增 `test_export_import_controls_use_transfer_routes`:断言工具栏含导出/导入按钮,脚本调用 `packs/export/status`、`packs/export/download`、`packs/import/stage`、`packs/import/apply`。
- [ ] **Step 6: 运行相关测试,确认新断言在当前代码上失败**

### Task 2: 后端路由与 handler 删除

**Files:**
- Modify: `mixins/web_routes.py`
- Modify: `mixins/pack_api.py`

**Interfaces:**
- Consumes: Task 1 的路由契约
- Produces: 9 条路由与对应 handler/helper 删除后的 `PackAPIMixin`

- [ ] **Step 1: `mixins/web_routes.py`**
  删除 `packs/export`、`packs/import`、`community/index/fetch`、`community/index/cache`、`community/install`、`settings/rules`、`settings/targets`、`settings/backup/export`、`settings/backup/import` 九条路由。
- [ ] **Step 2: `mixins/pack_api.py`**
  删除 `_api_export_pack`、`_api_import_pack`、`_api_fetch_community_index`、`_api_get_cached_community_index`、`_api_install_community_pack`、`_api_settings_rules`、`_api_settings_targets`、`_api_export_runtime_backup`、`_api_import_runtime_backup`。
- [ ] **Step 3: 删除 helper 并清理 import**
  删除 `_community_packs()`、`_public_export_result()`、`_decode_bounded_base64()`;用仓库搜索确认 `fetch_and_cache_community_index`、`find_cached_pack_entry`、`get_selection_rules`、`save_selection_rules`、`load_cached_community_index`、`install_pack_from_github_source`、`export_runtime_backup`、`import_runtime_backup`、`COMMUNITY_INDEX_URL` 等在本文件无残留引用后移除。
- [ ] **Step 4: 运行 `python -m unittest tests.test_web_route_capabilities tests.test_web_api_behavior tests.test_capture_index_api tests.test_pack_local_management -v` 与 `python -m compileall -q .`**

### Task 3: 前端页面删除与导航收敛

**Files:**
- Delete: `pages/a_manage/settings/`、`pages/a_manage/catalog/`
- Modify: `pages/a_manage/semantic/index.html`
- Modify: `pages/a_manage/semantic/script.js`

**Interfaces:**
- Consumes: Task 1 的页面契约
- Produces: 只剩语义页与跳转页的页面树

- [ ] **Step 1: 删除设置/资源广场目录**
  文本文件用 apply_patch,`.woff2` 移入 `%TEMP%\meme_manager_removed_assets`。
- [ ] **Step 2: `pages/a_manage/semantic/index.html`**
  移除 `<nav class="nav-actions">` 整块。
- [ ] **Step 3: `pages/a_manage/semantic/script.js`**
  移除 `allowedPages` 与 `applySecureNavLinks` 相关导航逻辑。
- [ ] **Step 4: 运行 `node --check` 与 Task 1 页面测试**

### Task 4: 表情索引页导出/导入实现

**Files:**
- Modify: `pages/a_manage/semantic/index.html`
- Modify: `pages/a_manage/semantic/script.js`
- Modify: `pages/a_manage/semantic/style.css`(如需)

**Interfaces:**
- Consumes: `packs/export/status`、`packs/export/download`、`packs/import/stage`、`packs/import/apply`
- Produces: 工具栏导出/导入交互

- [ ] **Step 1: 工具栏新增「导出当前资源包」按钮与模式选项(分享/带向量)**
  `packs/export/status` 返回 `vector_backup_available` 时启用带向量模式;`download("packs/export/download", { pack_id, mode })`。
- [ ] **Step 2: 工具栏新增「导入资源包」按钮与隐藏文件输入**
  `upload("packs/import/stage", file)` → 内联预检面板(名称/格式/数量/向量状态/警告)→ 确认(`packs/import/apply`,含 `set_as_default`、`overwrite`、`overwrite_manual_semantics`)→ 刷新资源包列表并提示。
- [ ] **Step 3: 缓存版本 bump 为 `20260817-transfer-1`**
- [ ] **Step 4: 运行 `node --check` 与页面/路由测试**

### Task 5: 文档与版本

**Files:**
- Modify: `README.md`、`CHANGELOG.md`、`metadata.yaml`、`main.py`
- Modify: `plan.md`、`task_plan.md`、`progress.md`、`findings.md`

- [ ] **Step 1: README** WebUI 段落改为「表情索引为唯一页面,含导出/导入」。
- [ ] **Step 2: CHANGELOG** 新增 `## [v2.3.0] - 2026-08-17`。
- [ ] **Step 3: metadata.yaml 与 main.py** 版本改为 v2.3.0。
- [ ] **Step 4: 工作记录** 更新。

### Task 6: 全量验证

- [ ] **Step 1: 运行完整验证门禁**
- [ ] **Step 2: 运行 SELF_CHECK 缺失 self / 路由-处理器检查**
- [ ] **Step 3: 复查 `git diff`,确认无残留引用**
