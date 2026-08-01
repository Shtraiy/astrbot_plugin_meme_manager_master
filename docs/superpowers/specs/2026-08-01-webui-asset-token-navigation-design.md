# WebUI Token 无效修复设计

## 背景

AstrBot 插件页在受限 iframe 中加载静态资源，并由宿主重写相对资源 URL、附加短期 `asset_token`。当前插件页面脚本自行读取并复制 `asset_token`，同时使用 `../` 在多个独立 Page 目录之间跳转。这样会把宿主生成的短期令牌带到不匹配或已过期的资源 URL，触发页面显示 `{"status":"error","message":"Token 无效"}`。

## 目标与非目标

目标：

- 不再由插件脚本读取、拼接或复制 `asset_token`。
- 页面切换不再依赖 `../` 跨越当前 Page 根目录。
- 保留现有页面之间的业务状态：`view` 与 `managed_pack_id`。
- 让宿主在每次打开目标插件 Page 时重新生成并注入有效的资源令牌。
- 增加静态回归测试，防止重新引入手动令牌处理和跨根目录链接。

非目标：

- 不修改后端 Web API、鉴权中间件或导入凭证 `import_token`。
- 不改变页面业务功能和 pack 管理逻辑。
- 不实现插件自己的令牌刷新机制。

## 方案

页面间导航统一使用 Dashboard 顶层 hash 路由：

`/#/plugin-page/meme_manager_master/<page_name>`

各页面保留 `data-nav-target` 作为逻辑目标名，例如 `catalog`、`settings`、`a_manage`、`semantic`。共享导航帮助函数把当前页面的业务参数附加到目标 Page 的 hash 查询部分，但不携带 `asset_token`。点击链接时跳出当前受限 iframe，让 Dashboard 重新挂载目标 Page 并生成新的静态资源 URL。

为兼容直接打开的页面和不同部署路径，路由基准从当前 `window.location` 的 origin 与 pathname 派生；若当前页面已经位于 Dashboard 的 hash 路由中，则仅替换插件 Page 名称，避免硬编码端口或主机名。页面目标只允许固定白名单，未知目标不生成导航 URL。

## 组件与数据流

- `pages/a_manage/api.js`：提供共享导航 URL 构造和链接初始化；只复制 `view`、`managed_pack_id` 等业务参数。
- `pages/catalog/script.js`、`pages/settings/script.js`、`pages/semantic/script.js`：改用共享的导航规则或等价实现，不再操作 `asset_token`。
- 各 Page 的 HTML：把相互跳转的 `href`/`data-nav-target` 从 `../.../index.html` 改为 Page 名称目标，并设置顶层导航目标。
- `pages/index.html`：保留入口重定向，但只重定向到管理 Page，不转发静态资源令牌。

流程：

1. Dashboard 打开插件 Page，并为该 Page 的静态资源生成令牌。
2. 页面脚本等待 `AstrBotPluginPage.ready()`。
3. 导航脚本读取当前 URL 中的业务参数，构造目标 Dashboard hash 路由。
4. 用户点击链接后由顶层 Dashboard 加载目标 Page。
5. AstrBot 为目标 Page 重新注入 bridge 和新的静态资源令牌。

## 错误处理

- 目标 Page 不在固定白名单时，导航帮助函数返回 `null`，不修改链接，避免生成任意路径。
- 缺失业务参数时不添加空查询项。
- 静态资源令牌由 AstrBot 完成生成、校验和生命周期管理；插件不显示或吞掉宿主错误。

## 测试策略

- 先新增静态回归测试，要求导航脚本不包含 `asset_token`，且页面间目标不包含 `../`。
- 测试目标 URL 仅包含允许的 Dashboard hash 路由和业务参数。
- 运行新增测试并确认其在旧实现上失败，再实施最小代码改动。
- 修改后运行全部 Python 测试、页面 JavaScript 语法检查和 `git diff --check`。

## 验收标准

- 仓库内页面导航不再手动转发 `asset_token`。
- 仓库内页面间导航不再使用 `../` 跨 Page 根目录。
- 新增回归测试与现有测试全部通过。
- 在 AstrBot WebUI 中刷新插件页后，管理页不再显示 `Token 无效`；页面切换后业务参数仍保留。
