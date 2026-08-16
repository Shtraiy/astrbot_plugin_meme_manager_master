# 移除表情包管理页面与死接口 — 设计文档

日期:2026-08-17

## 背景与目标

当前插件的 WebUI 中,「表情包管理」页(`pages/a_manage/index.html`)与「表情索引」页
(`pages/a_manage/semantic/index.html`)功能重叠:两页都支持按分类浏览表情缩略图、
删除与批量操作。用户决定保留表情索引,完全移除表情包管理页面,并一并清理:

- 表情包管理页专属的前端资源;
- 只被管理页调用的后端 Web API 与 handler;
- 顶层 `pages/semantic/`、`pages/settings/`、`pages/catalog/` 旧版页面副本。

插件 WebUI 入口改为直接进入表情索引。

## 范围

### 在范围内

- 删除 `pages/a_manage/` 根目录下管理页专属文件与资源。
- 删除顶层旧版页面副本目录。
- 删除只被管理页使用的 Web 路由与对应 mixin handler。
- 更新剩余页面导航,移除指向管理页的链接与导航白名单项。
- 更新 `pages/index.html` 重定向目标。
- 更新受影响的测试、README、CHANGELOG、版本号与工作记录。

### 不在范围内

- 保留「表情索引」「设置中心」「资源广场」三个页面的现有功能与交互。
- 保留被捕获流程、pack 运行时和聊天命令复用的底层后端函数
  (`add_emoji_to_category`、`scan_emoji_folder`、`set_default_pack`、
  `uninstall_pack`、`install_official_first` 服务等)。
- 保留聊天命令(`/查看图库`、`/添加表情`、`/恢复默认表情包`、`/清空指定类型`、
  `/清空全部`、`/图库统计`)及其后端依赖。
- 不重构剩余页面的布局、样式或交互逻辑。

## 前端变更

### 删除

`pages/a_manage/` 根目录下的管理页专属文件:

- `index.html`、`api.js`、`state.js`、`dialogs.js`、`emoji.js`、`pack.js`、
  `script.js`、`style.css`、`fa.min.css`、`webfonts/`

顶层旧版副本整目录:

- `pages/semantic/`、`pages/settings/`、`pages/catalog/`

### 修改

- `pages/index.html`:重定向改为
  `/#/plugin-page/meme_manager_master/a_manage/semantic`。
- `pages/a_manage/semantic/index.html`:移除「返回表情管理」链接。
- `pages/a_manage/settings/index.html` 与 `pages/a_manage/catalog/index.html`:
  移除指向 `../index.html` 的返回链接;导航仅保留表情索引、设置中心、资源广场。
- 剩余三个页面脚本中的导航白名单去掉 `a_manage`;
  `managed_pack_id` 与 `view` 参数传递逻辑保持不变。
- 内容发生变化的页面资源按惯例 bump 缓存版本号。

## 后端变更

### 删除的 Web 路由与 handler

`mixins/web_routes.py` 的 `ROUTES` 中删除以下路由(handler 同步删除):

| 路由 | handler |
|------|---------|
| `emoji`、`emoji/<category>`、`emoji/add/<category>`、`emoji/delete`、`emoji/batch_delete`、`emoji/move`、`emoji/batch_move`、`emoji/batch_copy`、`emoji/clear_all` | `_api_get_emojis`、`_api_get_emoji_by_category`、`_api_add_emoji`、`_api_delete_emoji`、`_api_batch_delete_emojis`、`_api_move_emoji`、`_api_batch_move_emojis`、`_api_batch_copy_emojis`、`_api_clear_all_emojis` |
| `emotions` | `_api_get_emotions` |
| `category/delete`、`category/clear`、`category/restore`、`category/rename`、`category/update_description`、`category/remove_from_config` | `_api_delete_category`、`_api_clear_category`、`_api_restore_category`、`_api_rename_category`、`_api_update_description`、`_api_remove_from_config` |
| `sync/status`、`sync/config` | `_api_sync_status`、`_api_sync_config` |
| `meme_image` | `_api_serve_meme_image` |
| `packs/default` | `_api_set_default_pack` |
| `packs/uninstall` | `_api_uninstall_pack` |
| `community/install_official_first` | `_api_install_official_first_pack` |

### 保留的 Web 路由

- `packs`、`packs/<pack_id>`:表情索引与设置/资源广场的资源包选择依赖。
- `packs/export*`、`packs/import*`:设置中心导入导出依赖。
- `meme_image_data`:表情索引缩略图预览依赖。
- `capture/*` 全部:表情索引工作台依赖。
- `settings/rules`、`settings/targets`、`settings/backup/export`、
  `settings/backup/import`:设置中心依赖。
- `community/index/fetch`、`community/index/cache`、`community/install`:
  资源广场依赖。

### 保留的底层能力

`backend/models.py` 的 `add_emoji_to_category`、`scan_emoji_folder` 等仍被捕获
流程与聊天命令使用;`backend/pack_storage.py` 的 `set_default_pack`、
`uninstall_pack` 仍被 pack 运行时使用;`install_official_first` 服务仍被
`/恢复默认表情包` 命令使用。这些函数与服务不删除,只删除 Web handler 层。

## 测试变更

按 TDD 先更新测试再删代码:

- `tests/test_web_route_capabilities.py`:期望路由表去掉被删路由,并新增断言
  被删路由不在任何 capability 表面注册。
- `tests/test_web_api_behavior.py`:删除针对已删 handler 的用例
  (`_api_get_emojis`、`_api_serve_meme_image` 相关),保留安全门、上传助手、
  `meme_image_data`、包操作与备份相关用例。
- `tests/test_webui_navigation_auth.py`:收敛到剩余三页;删除依赖
  `api.js`/`pack.js` 的运行时导航用例;保留入口重定向(目标更新)与缓存版本断言。
- `tests/test_capture_index_page.py`:双页面副本循环收敛为只检查
  `pages/a_manage/semantic/`。
- `tests/test_pack_local_management.py`:删除直接调用已删 handler
  (`_api_delete_emoji`、`_api_add_emoji`、`_api_batch_move_emojis`、
  `_api_clear_category`)的用例;其中仍有价值的包隔离/目录一致性断言迁移为
  直接调用 `backend/models.py` 底层函数(如 `delete_emoji_from_category`)的
  测试。`test_category_manager_can_update_selected_pack_metadata` 直接测试
  `CategoryManager`,保留。
- `tests/test_semantic_removal.py`:删除读取 `a_manage/index.html`、
  `emoji.js`、`pack.js`、`script.js` 的用例;保留语义移除相关断言。
- `tests/test_image_preview_ui.py`:该文件只测试被删管理页的预览弹窗逻辑,删除。

## 文档与版本

- `README.md`:WebUI 部分改为「入口即表情索引」;更新主要能力与验证命令
  (`node --check` 只覆盖剩余脚本)。
- `CHANGELOG.md`:新增 `v2.2.0` 条目(2026-08-17),记录移除内容与验证结果。
- `metadata.yaml` 与 `main.py` 注册版本统一升级为 `v2.2.0`。
- `docs/ARCHITECTURE.md`、`CONFIGURATION.md`:如涉及被删页面/接口的描述则同步更新。
- `plan.md`、`task_plan.md`、`progress.md`、`findings.md`:按项目惯例更新
  工作记录。

## 验证门禁

```powershell
python -m unittest discover -s tests
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
git diff --check
```

并运行 `docs/SELF_CHECK_WORKFLOW.md` 中的缺失 self / 已删符号 / 路由-处理器
一致性检查。

## 风险与兼容说明

- 删除后,WebUI 不再提供手动上传、分类改名/描述编辑、默认包切换;这些操作仍可
  通过聊天命令完成(`/添加表情`、`/查看图库`、`/恢复默认表情包`、
  `/清空指定类型`、`/图库统计`)。
- `meme_image` 直连接口当前无任何页面调用,一并移除;`meme_image_data` 保留。
- 旧的顶层页面 URL(如 `/#/plugin-page/meme_manager_master/semantic`)将失效,
  属于预期破坏性变更,已随版本说明记录。
