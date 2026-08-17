# 表情索引单页工作台优化 — 设计文档

日期：2026-08-17

## 背景与目标

当前 WebUI 已收敛为 `pages/a_manage/semantic/` 一个表情索引页，但页面仍以“功能按钮堆叠 + 两个列表”组织信息，首屏缺少明确的状态层级；前端脚本把资源包加载、v4 健康、轮询、选择、缩略图缓存、处置和导入导出全部放在一个初始化函数中，后端还保留了上一轮页面移除后失去调用方的兼容残留。

本次目标：

1. 在不改变现有 WebUI API、数据格式、聊天命令和核心操作语义的前提下，将表情索引页优化为 A 方案“信息总览”工作台。
2. 让用户按“资源包身份 → v4 健康 → 下一步任务 → 已整理内容”的顺序理解页面。
3. 抽取前端重复的轮询/状态更新逻辑，降低单一初始化函数的认知负担。
4. 删除确认没有运行时调用方的备份 facade、旧 import 和重复路径策略实现。
5. 保留现有测试覆盖的跨资源包防串、缓存淘汰、批量处置、导入导出和重索引恢复行为。

## 用户确认的设计方向

用户已确认采用 A「信息总览」方向，并要求继续深入：

- 顶部显示页面身份、当前资源包和低频全局操作。
- 中部使用 v4 健康总览作为视觉锚点。
- 待处理/需重建/重复项作为“下一步任务”优先展示。
- 已整理表情作为下方主要浏览区域。
- 所有当前 WebUI 功能仍在同一页面内；低频操作通过内联面板、确认弹窗或“更多操作”区域收纳。

## 范围

### 在范围内

- 修改 `pages/a_manage/semantic/index.html` 的页面层级和语义结构。
- 修改 `pages/a_manage/semantic/style.css`，建立顶部工具区、v4 健康卡片、任务区、健康明细和目录区的响应式布局。
- 修改 `pages/a_manage/semantic/script.js`，保持现有 DOM ID/API 路径兼容，同时抽取轮询、忙碌状态和重复状态更新逻辑。
- 更新 `tests/test_capture_index_page.py`、`tests/test_capture_index_runtime.py` 或新增同目录契约测试，保护新的层级与既有行为。
- 清理 `mixins/web_api.py` 中只存在于 import 区、且对应已删除 WebUI 功能的旧符号。
- 删除无生产调用方的 `PackBackupService` application facade 和 `backend/pack_backup.py`，同步清理导出和边界测试。
- 删除 `storage.py` 中被后续兼容包装器覆盖的本地路径策略实现，只保留 infrastructure policy 的兼容转发。
- 为前端资源更新缓存版本；不改变插件版本号和公开 API 契约，版本发布另行处理。

### 不在范围内

- 不恢复设置中心、资源广场或表情管理页面。
- 不改变 `capture/*`、`packs/*`、`meme_image_data` 的路由名、参数和响应字段。
- 不改变 `/偷取`、`/恢复默认表情包`、手动上传和聊天管理命令。
- 不删除仍被 `/恢复默认表情包` 使用的社区资源安装能力。
- 不删除仍被资源包导入导出流程使用的 pack transfer、selection rule 兼容数据，除非调用链验证证明其确实只属于已删除的运行时备份。
- 不引入新的前端框架或第三方运行时依赖。

## 功能映射

### 顶部身份与全局操作

保留现有 `#pack`、`#capture-refresh-button`、`#capture-export-button`、`#capture-import-button` 和隐藏文件选择器。布局上将资源包选择作为页面身份的一部分，刷新作为次级操作；导入导出仍打开原有内联传输面板，不新增页面跳转。

### v4 健康总览

保留 `#capture-v4-health`、`#capture-v4-ring-value` 和四个 `data-v4-filter` 按钮。健康卡片显示完整率、已整理、待分类、需重建、重复五类信息，点击状态仍只改变 `capture/workspace` 的 `v4_status` 查询，不改变后端统计口径。

### 任务操作区

保留全量语义重索引、分类索引待处理项、批量选择、当前页选择、待处理选择、选择索引、清空选择和一键忽略等既有控件。视觉上将它们分为主操作和次级批量操作，运行状态继续通过现有进度区和确认弹窗反馈。

### 工作内容区

- “等待分类处理”提升为第一内容区，展示 pending、needs_rebuild 和 duplicate 的处置入口。
- “索引健康明细”只复用 v4 统计字段，不新增独立后端查询。
- “已经整理好的表情”保留现有分页、分类筛选、缩略图缓存、预览和删除/处置语义，作为下方目录区。
- 保留隐藏的 `#capture-summary` 兼容节点，避免外部运行时测试和旧装配逻辑断裂；它不作为可见主摘要。

## 前端实现设计

### DOM 结构

在不随意更换已有行为选择器的前提下，将页面分成：

```text
main.layout
├── header.workspace-header
│   ├── page identity + pack selector
│   └── refresh / transfer actions
├── section.capture-v4-health
├── section.workspace-action-bar
├── section.capture-transfer-panel
├── section.capture-progress-row
├── section.workspace-content
│   ├── pending / attention panel
│   ├── health detail panel
│   └── indexed catalog panel + pagination
└── confirmation / preview overlays
```

已有功能 ID 尽量不改名；新节点只用于视觉分组和健康明细展示。脚本仍以 `querySelector` 获取行为节点，避免让既有 Node runtime harness 必须模拟一套新的组件框架。

### 样式策略

- 使用现有 CSS 变量和颜色体系，新增少量工作台语义变量：surface、border、muted、accent、danger。
- 首屏采用“窄顶部工具区 + 宽健康卡片 + 双栏任务区 + 目录网格”布局。
- 在宽屏使用 2 列任务区和 5 列缩略图，在窄屏自动降为单列/3 列。
- 主按钮只保留一个视觉强调色；导入导出、刷新和批量操作使用次级按钮样式。
- 保留 `prefers-reduced-motion`、键盘焦点、`aria-live`、`aria-pressed` 和隐藏状态规则。
- 不使用业务数据拼接 `innerHTML`；动态文本继续通过 `textContent` 写入。

### 脚本重构边界

在 `script.js` 内优先进行无行为变化的局部抽取：

1. 用统一的 polling controller 管理 reindex/index 两种轮询的停止、代际和下一次调度。
2. 抽取当前资源包/请求代际校验，继续阻止旧 pack 的异步结果覆盖新 pack。
3. 抽取按钮 `disabled`、`aria-busy` 和进度状态更新，避免两个任务流程各自维护相同状态。
4. 保留缩略图缓存的 LRU/字节上限、失败驱逐、原图不缓存和跨 pack 失效规则。
5. 不将脚本拆成需要浏览器 bundler 的新模块；当前 Node runtime harness 继续可以直接加载单个 `script.js`。

## 后端清理设计

### 删除无调用方的备份 facade

仓库搜索显示 `PackBackupService` 只在 `manager_base.py` 初始化、application 导出和测试中出现，没有生产调用方；`backend/pack_backup.py` 只为该 facade 转发。实施时删除：

- `manager_base.py` 的 `PackBackupService` import 和 `self.pack_backup_service` 初始化。
- `application/services.py` 的 `PackBackupService`。
- `application/__init__.py` 的导出。
- `backend/pack_backup.py`。
- 仅验证该 facade 的 application/boundary 测试。

运行时备份函数是否从 `backend/pack_storage.py` 删除，必须先根据 import/export 和历史数据兼容调用链单独验证；如果仍被 pack transfer 或外部兼容入口依赖，则本次只删除 facade，不删除底层函数。

### 清理 WebAPI 残留 import

`mixins/web_api.py` 中以下符号当前仅位于 import 区，且不再对应已注册 Web 路由：运行时备份、社区索引、选择规则、旧 pack 安装和旧卸载相关函数。实施时用 AST/仓库搜索确认后删除 import，并保留仍被 `/恢复默认表情包` 或 pack transfer 使用的底层实现。

### 收敛路径策略兼容层

`storage.py` 先在 1290 行附近定义本地路径策略，后在 1388 行附近重新定义同名兼容包装器；实际运行使用后者。保留末尾的 infrastructure 转发实现，删除前一组不可达重复实现，并保持 `storage.py` 对历史调用方的导出名称不变。

## 错误处理与兼容性

- 页面加载失败、资源包为空和 API 失败继续显示在 `#notice`，不通过未转义 HTML 注入业务数据。
- 导入导出继续使用现有预检、凭证、下载和确认流程。
- 重索引/分类索引轮询继续在任务完成、失败、切换资源包和页面刷新时停止或失效；旧请求不得覆盖新 workspace。
- 删除/忽略失败项继续保留选择状态并标记失败卡片。
- 后端删除只针对仓库内确认无生产调用方的 facade/import，不改变路由注册表中保留的页面能力。

## 测试策略

### 先行契约测试

- 页面契约测试验证新的 workspace 分区、v4 健康区、任务区、目录区和缓存版本。
- 后端边界测试验证 `PackBackupService` 不再由 manager 组装，且 `application` 不再导出已删除 facade。
- storage boundary 测试继续验证安全分类路径和 extension 行为。

### 既有行为回归

继续运行现有 Node runtime harness，覆盖：

- 删除/忽略/批量处置与部分失败恢复。
- 重索引和分类索引轮询、进度、失败和跨 pack 失效。
- 缩略图缓存 LRU、字节上限、失败重试和跨 pack 清理。
- 导入导出控件和路由调用。
- 页面导航、无旧页面链接、无手动 token 转发。

### 验证门禁

```powershell
python -m unittest discover -s tests
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
git diff --check
```

## 完成标准

- A 方案布局在宽屏和窄屏均保持清晰的状态层级，首屏能看见资源包身份、v4 健康和下一步任务。
- 当前 WebUI 功能全部仍可从该页面完成；没有恢复跨页面导航。
- 前端脚本的轮询/状态重复逻辑被收敛，既有 runtime harness 全部通过。
- `PackBackupService` facade、旧 import 和 `storage.py` 重复策略实现被清理；保留能力的路由与底层兼容入口不受影响。
- 全量测试、编译、schema、architecture、Node 语法和 diff 门禁通过。

