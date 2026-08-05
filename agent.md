# meme_manager_master 项目级 Agent 指南

本文件是本仓库的项目级 AI 编程代理规范。任何代理开始工作前都应先阅读本文件，再读取与当前任务相关的源码、测试和文档。

## 1. 项目身份

`meme_manager_master` 是面向 AstrBot `>=4.5.7,<5` 的表情包管理插件，提供：

- 多 pack 存储、分类、导入导出、备份和运行时切换；
- WebUI 浏览、上传、预览、移动、删除、标签管理和索引维护；
- 群聊图片识别、分类、自动收集和按场景选择表情包；
- 可选的语义能力，但语义依赖不能阻塞核心启动、基础上传或普通选图流程。

运行数据默认位于 `AstrBot/data/plugin_data/meme_manager_master/`。插件只管理自己的数据目录，不得读取、覆盖或混用原版 `meme_manager` 的数据目录。

## 2. 开始任务前

按以下顺序建立上下文：

1. 阅读本文件、`README.md`、`CONFIGURATION.md`、`CHANGELOG.md`、`metadata.yaml` 和 `docs/ARCHITECTURE.md`。
2. 检查工作区状态：

   ```powershell
   git status --short
   git diff --stat
   ```

3. 只阅读与当前任务相关的源码、测试、WebUI 文件和最近提交；不要把 `.git`、`.worktrees`、`__pycache__`、`.pytest_cache` 或构建产物当作源码。
4. 如果发现已有未提交修改，先区分它们和当前任务，保留原修改，不得执行 `git reset --hard`、`git checkout --` 或大范围覆盖。
5. 对涉及多个模块的改动先列出最小变更计划；实现前先确定受影响的边界、测试和文档。

## 3. 目录职责与依赖方向

### 入口与运行时

- `main.py`、`init.py`：AstrBot 插件入口、生命周期和组合对象。
- `config.py`、`runtime_config.py`：配置定义、兼容读取和运行时参数。
- `manager_base.py`：兼容旧入口的管理器基础行为。

### 稳定边界

- `domain/`：领域模型和分类映射，不依赖 WebUI 或具体存储实现。
- `ports/`：跨层契约和稳定接口。
- `application/`：应用服务和 Web 路由编排，依赖 domain/ports，不直接承载底层文件细节。
- `infrastructure/`：路径边界、存储适配器、pack runtime、catalog、图片仓库和选择状态等 ports 的实现。
- `capabilities/`：可选能力适配器，例如语义能力。

目标依赖方向：

```text
入口/适配器 → application → domain / ports
infrastructure → domain / ports
可选 capability → ports
```

### 兼容层与功能模块

- `backend/`：pack、分类、标签、语义兼容、远程下载和备份等后端模块；`storage.py` 与 `backend/pack_storage.py` 当前仍可能是兼容 facade，迁移时不得未经验证直接删除旧入口。
- `mixins/`：命令、事件、Web API、Web 路由、pack API、表情 API 和捕获索引 API；修改 mixin 时必须检查组合类、路由处理器和实例方法绑定。
- `capture.py`、`capture_pipeline.py`、`collector.py`、`capture_activity.py`、`capture_components/`：识别、分类、收集、索引和活动状态流程。
- `meme_selection.py`、`response_policy.py`：选图、权重、发送凭证和回复策略。
- `pages/`：原生 HTML/CSS/JavaScript WebUI；页面脚本按 `state.js`、`api.js`、`dialogs.js`、`pack.js`、`emoji.js` 和入口 `script.js` 分工。
- `tests/`：以 Python `unittest` 为主的回归测试，测试文件名为 `test_*.py`。
- `scripts/`：配置 schema 生成、架构边界检查和架构指标脚本。

## 4. 不可破坏的架构与安全规则

1. 用户提供的 pack、分类、文件名和路径必须经过 `PackContext`、`PackPaths` 或 `PathBoundary` 校验，并保持在选定 pack 内。
2. 不允许通过绝对路径、`..`、符号链接逃逸、非法 pack ID 或 Windows 特殊路径访问插件数据根目录之外的文件。
3. 图片读取 API 只读取允许的图片文件；上传、导入、备份、导出和归档必须执行大小、类型、路径和原子写入校验。
4. pack 的 manifest、catalog、metadata、index 和图片文件必须保持一致；涉及写操作时沿用现有锁、事务和原子写入边界。
5. 选择、捕获、WebUI 管理和自动收集必须绑定当前活动 pack；切换默认 pack 后不得继续写入旧目录。
6. 语义/向量模块是可选能力。缺少 provider 或 FAISS 时，核心启动、普通上传、分类、基础索引和选图不能因导入失败而中断。
7. 保持现有 WebUI 路由、配置键、pack 格式、命令和 mixin 入口兼容，除非任务明确要求破坏性变更并补充迁移说明。
8. 日志和交付摘要不得暴露图片绝对路径、凭据、完整用户隐私内容或不必要的第三方信息。
9. 不在源码、metadata、日志或提交信息中写入 API key、token、密码、cookie 或本机隐私路径。

## 5. 标准开发流程

### 5.1 变更前

- 明确用户可见行为、影响模块、数据格式和兼容要求。
- 找到现有实现和对应测试；优先复用现有边界、原子写入、错误类型和测试 fake。
- 对 bug 或回归问题先写能复现原行为的测试，再修改实现。
- 对配置、路由、存储、WebUI 或 mixin 改动，同时规划失败路径测试。

### 5.2 实现中

- 保持最小变更；不进行无关重构、格式化或批量重命名。
- 一个模块只承担清晰职责；跨层调用通过 application service 或 ports，不从 domain 反向依赖 WebUI/基础设施。
- 新增或修改行为时同步更新针对性测试、必要文档和 `CHANGELOG.md`。
- 删除或移动方法后，使用仓库搜索确认没有旧调用、旧路由处理器或旧 import。
- 修改 JavaScript 后对所有受影响的 `.js` 文件运行 `node --check`；页面实际交互仍需在 AstrBot WebUI 中人工确认。

### 5.3 完成前

1. 查看 `git diff`，确认没有误改、调试输出、临时文件或敏感信息。
2. 运行适用的目标测试和第 6 节的常规验证门禁。
3. 更新日志、元数据和 schema（规则见第 7 节）。
4. 再次运行 `git diff --check` 和工作区检查。
5. 仅暂存当前任务相关文件，按第 8 节自动创建本地 commit。
6. 在交付摘要中记录变更、验证命令、commit ID、未验证项和是否执行远程上传。

## 6. 验证门禁

### 6.1 常规 Python 验证

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
git diff --check
```

### 6.2 WebUI 验证

```powershell
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object {
    node --check $_.FullName
}
```

涉及页面路由、鉴权、静态资源 token、图片预览、上传、导入导出或删除时，必须运行对应回归测试，并在可用的 AstrBot WebUI 中完成真实交互确认。

### 6.3 结构和安全变更

- 跨模块结构变更：额外运行 `python scripts/architecture_metrics.py --top 20`，并阅读架构检查输出。
- 安全、远程下载、文件归档、导入导出或路径边界变更：补充边界/拒绝路径测试；环境具备工具时运行 `bandit -r backend mixins -q` 和 `pip-audit -r requirements.txt`。
- 真实 AstrBot host、认证 middleware、provider、DNS 或外部网络行为无法在本地复现时，必须明确标记为“未验证”，不得宣称已通过。

验证命令失败时，不得创建 commit；先报告失败命令、首个错误和受影响范围，修复后重新运行完整适用门禁。

## 7. 日志、版本和元数据同步

### 7.1 `CHANGELOG.md`

- 用户可见功能、修复、安全行为、数据迁移、兼容性和架构交付都要更新 `CHANGELOG.md`。
- 若当前没有发布版本，先在文件顶部创建 `[Unreleased]`；已有发布节时保持 Keep a Changelog 结构和 Asia/Shanghai 日期格式。
- 条目写清“改了什么、影响谁、是否需要迁移、如何验证”；不要只写内部文件名。
- 测试数量只写本次新鲜验证得到的结果，不沿用过期数字。

### 7.2 `metadata.yaml` 与 README

- 只有实际发布版本变化时才修改 `metadata.yaml:version`，并同步 README 的版本徽章或版本说明。
- 修改 AstrBot 最低版本、依赖、插件名称、命令或功能描述时，同步检查 `metadata.yaml`、README 和 `CONFIGURATION.md`。
- 不为普通 bugfix 随意递增版本；版本号变更必须在 `CHANGELOG.md` 中有对应发布条目。

### 7.3 `_conf_schema.json`

- 配置定义以 `runtime_config.PluginConfig` 为源；不要手工编辑生成文件。
- 配置定义变化后运行：

  ```powershell
  python scripts/generate_conf_schema.py --write
  python scripts/generate_conf_schema.py --check
  ```

- schema 漂移检查失败时，先提交生成结果与对应配置定义变更，不能只修改 `_conf_schema.json` 掩盖漂移。

### 7.4 代理流程更新日志

每次修改本文件时，在文末追加日期、版本、变更内容和原因；不要删除旧记录。项目功能变更的运行日志仍写入 `CHANGELOG.md`，不要把产品变更混入本节。

## 8. 自动 commit 与远程上传

### 8.1 自动本地 commit

本项目默认要求：适用验证全部通过后，代理自动创建本地 commit。

执行前必须：

1. 确认当前分支和工作区状态。
2. 只暂存当前任务相关文件；保留用户已有修改，不使用全量 `git add .` 覆盖边界。
3. 查看 staged diff，确认不含密钥、临时文件、缓存、构建产物或无关修改。
4. 运行 `git diff --cached --check`。
5. 使用 Conventional Commits 前缀：`feat`、`fix`、`refactor`、`docs`、`test`、`chore` 或 `security`。

推荐格式：

```text
<type>: <简短、可识别的变更说明>

Summary: <关键变更>
Tests: <实际运行的命令和结果>
Metadata: <CHANGELOG/schema/metadata 是否同步>
```

如果 `.git` 写权限不足，先请求受控 Git 写权限；不要删除 lock 文件、修改 Git 配置或绕过门禁。commit 成功后记录短 commit ID，并再次运行 `git status --short`。

### 8.2 远程 push

`git push` 不属于默认自动流程。只有用户或当前任务明确授权上传时，代理才可以：

1. 检查当前分支、远程 URL 和待推送 commit。
2. 确认没有需要保留的未提交修改。
3. 使用明确的远程和分支执行 push；禁止强制推送、覆盖远程历史或推送凭据。
4. 在交付摘要中记录远程、分支和结果。

没有明确授权时，只报告本地 commit 已完成，并说明远程 push 未执行。

## 9. 交付摘要格式

每次任务结束时使用以下结构：

```markdown
变更：
- <文件/功能及用户可见影响>

验证：
- `<命令>`：<通过/失败及关键结果>

文档与元数据：
- CHANGELOG：<已更新/不适用及原因>
- metadata.yaml / README：<已同步/不适用及原因>
- _conf_schema.json：<已生成并检查/不适用及原因>

Git：
- Commit：<短 ID 和提交信息>
- Push：<已执行的远程/分支，或“未执行，等待明确授权”>

限制：
- <真实 host、外部 provider、网络或其他未验证项>
```

## 10. 流程更新日志

| 日期 | 版本 | 变更 | 原因 |
| --- | --- | --- | --- |
| 2026-08-05 | 1.0 | 建立项目级 AI 代理规范，纳入测试门禁、CHANGELOG、元数据/schema 刷新、本地自动 commit 和远程 push 授权规则。 | 统一整个项目的自动化开发与交付流程。 |
