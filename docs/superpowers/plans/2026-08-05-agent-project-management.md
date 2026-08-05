# Project Agent Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在项目根目录创建一份可供 AI 编程代理执行的 `agent.md`，统一描述项目结构、验证门禁、日志/元数据同步和自动本地提交流程。

**Architecture:** 采用单文件项目规范，不修改插件运行代码和现有 CI。文档把项目知识、不可破坏边界、标准工作流、元数据刷新、验证命令和 Git 交付策略组织为独立章节；自动化动作止于本地 commit，远程 push 始终需要明确授权。

**Tech Stack:** Markdown、Python `unittest`、Python `compileall`、Node.js `--check`、Git、现有 GitHub Actions 工作流。

## Global Constraints

- 只新增项目级文档，不修改插件运行代码、现有 CI 工作流或远程仓库配置。
- 默认自动化动作止于本地 `git commit`；`git push` 只有当前任务明确授权时才允许执行。
- 保持入口/适配器 → application → domain/ports，infrastructure 实现 ports 的依赖方向。
- 用户路径必须经过 `PackContext` 或 `PathBoundary`；可选语义能力不能阻塞核心启动。
- 不得重置、覆盖或提交与当前任务无关的用户修改。

---

### Task 1: Create the project-level agent workflow document

**Files:**
- Create: `agent.md`
- Reference: `README.md`, `CONFIGURATION.md`, `CHANGELOG.md`, `metadata.yaml`, `docs/ARCHITECTURE.md`, `.github/workflows/test.yml`, `scripts/generate_conf_schema.py`
- Verify: `agent.md` content checks, `git diff --check`

**Interfaces:**
- Consumes: current repository structure, architecture contracts and CI commands.
- Produces: a root-level AI-agent policy with explicit commit, metadata and remote-upload rules.

- [x] **Step 1: Write the document sections**

  Include project identity, directory responsibilities, architecture invariants, safe editing rules, standard change workflow, `CHANGELOG.md` rules, metadata/schema refresh rules, automatic commit policy, remote push policy, delivery summary format and a process-update log.

- [x] **Step 2: Check repository-specific commands**

  Ensure the documented commands match the repository:

  ```powershell
  python -m unittest discover -s tests -v
  python -m compileall -q .
  python scripts/generate_conf_schema.py --check
  python scripts/check_architecture.py
  Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
  git diff --check
  ```

- [x] **Step 3: Check safety and scope language**

  Confirm that the document says to preserve unrelated worktree changes, stage only task files, refuse to commit after failed verification, and never push without explicit authorization.

- [x] **Step 4: Review and commit**

  Run:

  ```powershell
  git diff --check
  git status --short
  git add -- agent.md docs/superpowers/plans/2026-08-05-agent-project-management.md
  git commit -m "docs: add project agent management guide"
  ```

  Expected: no whitespace errors; only the requested documentation files are staged; commit succeeds locally; no `git push` is performed.
