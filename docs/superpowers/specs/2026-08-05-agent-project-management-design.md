# 项目级 AI 代理管理规范设计

## 目标

在项目根目录新增 `agent.md`，作为 `meme_manager_master` 项目的统一 AI 编程代理入口。它既描述项目结构和不可破坏的架构边界，也规定从修改、验证、文档同步到本地提交的完整交付流程。

## 范围

本次只新增项目级文档，不修改插件运行代码、现有 CI 工作流或远程仓库配置。默认自动化动作止于本地 `git commit`；`git push` 不自动执行，只有当前任务明确授权时才允许上传远程。

## `agent.md` 内容设计

### 1. 项目身份与目录地图

说明插件面向 AstrBot，列出入口、应用服务、领域模型、端口、基础设施、兼容 facade、WebUI、测试和维护脚本的职责，以及 pack 数据边界。

### 2. 架构与安全不变量

代理必须保持入口/适配器 → application → domain/ports，infrastructure 实现 ports 的依赖方向；用户路径必须经过 `PackContext` 或 `PathBoundary`；语义能力保持可选且不能阻塞核心启动；现有 WebUI 路由、配置键、pack 格式和 mixin 入口默认保持兼容。

### 3. 标准工作流

规定读取 `README.md`、`CONFIGURATION.md`、`metadata.yaml`、相关架构文档和近期提交，检查工作区，制定最小变更计划，先补测试再实现，最后执行分层验证。发现已有未提交修改时只能避开无关文件，不得重置或覆盖。

### 4. 日志与元数据同步

用户可见行为、修复和架构变化必须更新 `CHANGELOG.md`；发布版本变化时同步 `metadata.yaml` 与 README 版本信息；配置定义变化时使用 `scripts/generate_conf_schema.py --write` 生成 `_conf_schema.json`，再使用 `--check` 验证。每次代理运行都在交付摘要中记录变更、验证结果、commit 和未执行的远程上传。

### 5. 验证门禁

根据改动范围运行目标测试；常规交付至少运行 unittest、compileall、schema check、架构检查、前端 JavaScript 语法检查和 `git diff --check`。安全相关变更追加 Bandit 与 pip-audit；涉及真实 AstrBot host 的行为要明确标记为未验证。

### 6. 自动 commit 规则

只有所有适用验证通过后才允许自动提交；只暂存当前任务相关文件；提交信息使用 Conventional Commits 风格；提交正文记录验证命令和结果。验证失败时不得 commit，只需报告失败原因和下一步。`git push` 默认关闭，明确授权后才检查分支/远程并执行。

### 7. 流程更新日志

在文档末尾维护规范本身的版本、日期和变更原因，便于后续代理识别流程规则何时变化。

## 验收标准

- 根目录存在可直接供 AI 代理读取的 `agent.md`。
- 文档明确覆盖项目结构、开发流程、测试门禁、CHANGELOG、元数据/schema 刷新、本地自动 commit 和远程上传限制。
- 文档中的命令与当前 `.github/workflows/test.yml`、README 和现有脚本一致。
- 文档不要求危险的重置、强制覆盖、凭据写入或未经授权的远程推送。
