# 移除设置中心与资源广场,导出/导入移植到表情索引 — 设计文档

日期:2026-08-17

## 背景与目标

v2.2.0 已移除表情包管理页,WebUI 收敛为表情索引、设置中心、资源广场三页。用户决定继续收敛:

- 删除设置中心与资源广场页面;
- 把设置中心的「表情包导出」「表情包导入」移植到表情索引页;
- 设置中心的选择规则、运行时备份随页面移除,不移植;
- 资源广场的官方/社区安装入口移除,聊天命令 `/恢复默认表情包` 与相关底层服务保留。

版本升级为 v2.3.0。

## 范围

### 在范围内

- 删除 `pages/a_manage/settings/` 与 `pages/a_manage/catalog/` 整目录。
- 表情索引页工具栏新增导出/导入控制。
- 删除只被这两页使用的 Web 路由与 handler。
- 更新测试、README、CHANGELOG、版本号与工作记录。

### 不在范围内

- 保留 AstrBot 页面发现入口:`pages/a_manage/index.html` 跳转页(跳表情索引)。
- 保留表情索引页现有交互与后端接口。
- 保留 `packs/export/status`、`packs/export/download`、`packs/import/stage`、
  `packs/import/apply`、`packs` 列表/详情、`capture/*`、`meme_image_data`。
- 保留聊天命令与底层服务(`install_official_first`、pack 导入导出、备份相关底层函数)。

## 前端变更

### 删除

- `pages/a_manage/settings/`(index.html、script.js、style.css、fa.min.css、webfonts/)
- `pages/a_manage/catalog/`(index.html、script.js、style.css、fa.min.css、webfonts/)

### 表情索引页新增(工具栏)

- **导出当前资源包**:按钮 + 分享版/带向量备份模式选择;`packs/export/status` 检测
  `vector_backup_available`,仅可用时允许选择带向量模式;下载走
  `packs/export/download`(mode = share | backup)。
- **导入资源包**:按钮 + 隐藏文件选择;zip 通过 `packs/import/stage` 预检后显示内联确认
  (名称/格式/图片数/语义数/向量状态/警告),含「设为默认」「覆盖」选项;确认后调用
  `packs/import/apply`,完成后刷新资源包列表并提示结果。

### 导航

- 表情索引页移除顶部「设置中心」「资源广场」导航链接,页面不再有跨页导航。
- 移除脚本中的 `applySecureNavLinks`/`allowedPages` 导航逻辑(保留其余现有逻辑)。
- 入口仍为 `pages/index.html` → `/#/plugin-page/meme_manager_master/a_manage` →
  `pages/a_manage/index.html` 跳转页 → `./semantic/index.html`。

## 后端变更

### 删除的 Web 路由与 handler

| 路由 | handler |
|------|---------|
| `packs/export`(旧 POST) | `_api_export_pack` |
| `packs/import`(旧 POST) | `_api_import_pack` |
| `community/index/fetch`、`community/index/cache`、`community/install` | `_api_fetch_community_index`、`_api_get_cached_community_index`、`_api_install_community_pack` |
| `settings/rules`、`settings/targets` | `_api_settings_rules`、`_api_settings_targets` |
| `settings/backup/export`、`settings/backup/import` | `_api_export_runtime_backup`、`_api_import_runtime_backup` |

同步删除 `pack_api.py` 中仅被上述 handler 使用的辅助:
`_community_packs()`、`_public_export_result()`、`_decode_bounded_base64()`,并清理
不再使用的 import(社区索引、选择规则、运行时备份相关)。

### 保留的 Web 路由

- `packs`、`packs/<pack_id>`:表情索引资源包选择依赖。
- `packs/export/status`、`packs/export/download`:表情索引导出功能依赖。
- `packs/import/stage`、`packs/import/apply`:表情索引导入功能依赖。
- `capture/*` 全部、`meme_image_data`:表情索引工作台依赖。

### 保留的底层能力

`export_pack_archive`、`get_pack_export_capabilities`、`inspect_pack_archive`、
`import_pack_archive`、`list_installed_packs`、`get_pack_detail` 以及
`community_pack_source` 服务(供 `/恢复默认表情包` 命令)保留。

## 测试变更

- `tests/test_web_route_capabilities.py`:被删路由加入禁止注册断言;保留路由断言
  更新为 `packs/import/stage`、`packs/import/apply`、`packs/export/download` 等。
- `tests/test_web_api_behavior.py`:删除社区路由、备份解码、导出结果脱敏等针对已删
  handler/helper 的用例;保留导入凭证、包操作与安全相关用例。
- `tests/test_webui_navigation_auth.py`:剩余页面收敛为 `a_manage` 跳转页与表情索引页;
  断言表情索引页无设置/资源广场链接;缓存版本断言只保留表情索引页。
- `tests/test_semantic_removal.py`:删除对 `pages/a_manage/settings/script.js` 的读取。
- `tests/test_capture_index_page.py`:新增表情索引页导出/导入控制断言(按钮存在、脚本
  调用 `packs/export/status`、`packs/export/download`、`packs/import/stage`、
  `packs/import/apply`)。

## 文档与版本

- `README.md`:WebUI 段落改为「表情索引是唯一页面,包含浏览/处置/语义索引与包导出导入」。
- `CHANGELOG.md`:新增 v2.3.0 条目。
- `metadata.yaml` 与 `main.py` 注册版本统一为 v2.3.0。
- `plan.md`、`task_plan.md`、`progress.md`、`findings.md`:按项目惯例更新。

## 验证门禁

```powershell
python -m unittest discover -s tests
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
git diff --check
```

并运行 `docs/SELF_CHECK_WORKFLOW.md` 的缺失 self / 路由-处理器一致性检查。

## 风险与兼容说明

- 删除后,选择规则、运行时备份、社区/官方资源广场安装失去 WebUI 入口;官方包安装仍可
  通过 `/恢复默认表情包` 命令完成。
- 表情包导出/导入为完整迁移,不损失能力;导入仍支持覆盖与设为默认选项。
- 页面入口链路保持不变(AstrBot 仅发现 `pages/<page_name>/index.html` 一级页面,
  `a_manage` 跳转页是唯一可发现页面)。
