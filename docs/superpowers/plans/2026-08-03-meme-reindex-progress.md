# 重索引进度条 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为重索引操作增加可查询的后台进度，并在两个索引页面的按钮下显示进度条和当前分类。

**Architecture:** `CaptureIndexAPIMixin` 为每个资源包维护内存中的重索引任务状态；POST 接口只负责启动任务，GET 接口返回状态。重索引仍调用 `MemeStore.reindex_all_categories()`，不调用模型；页面在任务期间轮询状态并更新进度条。

**Tech Stack:** Python 3、Quart Web API、原生 JavaScript、CSS、unittest、Node `--check`。

## Global Constraints

- 重索引只修改文件名、catalog 的 `filename`/`id`，不得调用模型或改变已有索引元数据。
- 进度必须按文件数报告，且包含当前分类、已完成数、总数和状态。
- 两套索引页面 `pages/semantic` 与 `pages/a_manage/semantic` 保持相同交互行为。
- 不自动提交 Git，保留工作区已有改动。

---

### Task 1: Add backend progress state and APIs

**Files:**
- Modify: `mixins/capture_index_api.py`
- Modify: `mixins/web_routes.py`
- Test: `tests/test_capture_index_api.py`
- Test: `tests/test_web_route_capabilities.py`

- [x] Add failing tests for a POST-started task and a GET progress response.
- [x] Add pack-scoped task state with `status`, `processed`, `total`, `current_category`, and `message`.
- [x] Run reindex in an asyncio task and update state after each category/file batch.
- [x] Add `capture/reindex/status` GET route and return completed/error states.
- [x] Run focused API and route tests.

### Task 2: Add progress UI to both pages

**Files:**
- Modify: `pages/semantic/index.html`, `pages/semantic/script.js`, `pages/semantic/style.css`
- Modify: `pages/a_manage/semantic/index.html`, `pages/a_manage/semantic/script.js`, `pages/a_manage/semantic/style.css`
- Test: `tests/test_capture_index_page.py`

- [x] Add failing source-contract assertions for progress markup, polling, and status text.
- [x] Add a progress bar below the reindex button with accessible value text.
- [x] Poll `capture/reindex/status` while active and stop polling on completion/error.
- [x] Keep the button disabled only for the page's own active task.
- [x] Run focused page tests and Node syntax checks.

### Task 3: Full verification

- [x] Run `python -m unittest discover -s tests -p "test_*.py" -v`.
- [x] Run both Node syntax checks.
- [x] Run `git diff --check` and inspect the changed-file list.
