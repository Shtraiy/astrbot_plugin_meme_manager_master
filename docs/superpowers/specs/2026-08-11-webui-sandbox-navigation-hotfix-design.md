# WebUI Sandbox 导航回归修复设计

## 背景

`v2.1.3` 将插件页面之间的链接改成 Dashboard hash 路由，并为链接设置了 `target="_top"`，目的是让 Dashboard 重新挂载目标 Page 并刷新静态资源令牌。

该方案忽略了 AstrBot Plugin Page 的 iframe sandbox 只允许脚本、表单和下载，不允许插件页面导航顶层窗口。浏览器因此拦截 `_top` 跳转，表现为“表情索引”和“设置中心”点击后没有反应。

## 目标

- 恢复 `a_manage` 页面内“表情索引”“设置中心”“资源广场”的可点击导航。
- 不再生成或设置 `target="_top"`。
- 继续保留 `managed_pack_id` 与 `view` 业务参数。
- 用运行时测试验证链接在 sandbox 中采用当前 iframe 导航，而不是只检查源码字符串。

## 方案比较

### 方案一：恢复 `a_manage` Page 根目录内的相对导航（采用）

主页面使用 `./semantic/index.html`、`./settings/index.html` 和 `./catalog/index.html`；嵌套页面使用同一 `a_manage` 根目录内的相对链接。链接不设置 `_top`，由当前 iframe 执行导航。现有两份页面副本和业务脚本无需重构，改动最小。

代价是静态资源仍遵循 AstrBot 的短期 token 生命周期；用户长时间停留后若 token 已过期，需要刷新当前插件 Page。插件侧没有受支持的导航 Bridge，不能安全地要求 Dashboard 刷新 token。

### 方案二：重构为单文档 SPA

把管理、索引、设置和资源广场合并到一个 HTML 文档，以 hash 切换视图。可完全避免二次 HTML 导航，但需要重构多份大型页面、样式与初始化脚本，超出本次回归修复范围。

### 方案三：扩展 AstrBot Dashboard Bridge

在 AstrBot 核心新增受控的 Page 导航动作，由父窗口调用 Vue Router。这是长期最完整的方案，但不属于插件仓库可独立交付的修改。

## 组件修改

- `pages/a_manage/index.html`：恢复三个同根相对链接，移除 `_top`。
- `pages/a_manage/api.js`：停止把链接重写成 Dashboard 路由，只移除不安全的 `target`。
- `pages/a_manage/{semantic,settings,catalog}/index.html`：恢复同一 Page 根目录内的相对导航。
- 三份嵌套页面脚本：删除 Dashboard `_top` 重写逻辑，保留业务参数时仅更新相对 URL 查询参数。
- `tests/test_webui_navigation_auth.py`：新增 sandbox 导航契约，禁止 `_top` 并要求 `a_manage` 页面使用 iframe 内相对链接。

## 参数与错误处理

导航初始化从当前 URL 读取 `view`、`managed_pack_id`，仅将这两个业务参数附加到相对目标 URL。未知 `data-nav-page` 不改写。静态资源令牌继续完全由 AstrBot 注入，插件不读取、不复制、不记录 `asset_token`。

## 验收

- 表情管理页点击“表情索引”和“设置中心”会改变当前 iframe 文档，不再被 sandbox 拦截。
- 所有 `a_manage` 导航链接均不包含 `target="_top"`。
- 业务参数能够保留，`asset_token` 不由插件脚本处理。
- 导航回归测试、相关页面测试、全部页面 JavaScript 语法检查通过。
