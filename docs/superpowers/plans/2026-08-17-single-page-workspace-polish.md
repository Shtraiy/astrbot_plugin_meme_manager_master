# 表情索引单页工作台优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持现有 WebUI API、数据结构和聊天命令不变的前提下，将表情索引页优化为 A 方案信息总览工作台，抽取前端重复状态逻辑，并清理确认无生产调用方的后端残留。

**Architecture:** 保留现有单文件 `script.js` 和 DOM 行为 ID，先通过 HTML/CSS 重排建立“身份与操作 → v4 健康 → 下一步任务 → 已整理目录”的页面层级，再在脚本内部抽取通用轮询控制器与任务状态更新器。后端只删除 `PackBackupService` facade、无效 WebAPI import 和 `storage.py` 被覆盖的重复策略实现；资源包 transfer、社区安装和现有路由不变。

**Tech Stack:** HTML5、CSS3、原生 ES modules/JavaScript、Python 3、`unittest`、Node.js `node --check`、现有 Node runtime harness。

## Global Constraints

- 不改变 `capture/*`、`packs/*`、`meme_image_data` 的路由名、参数和响应字段。
- 不恢复设置中心、资源广场或表情管理页面，不新增前端框架和第三方运行时依赖。
- 保留 `/偷取`、`/恢复默认表情包`、手动上传和聊天管理命令。
- 保留缩略图缓存 LRU/字节上限、跨资源包失效、批量处置、导入导出和重索引恢复行为。
- 不触碰 `.brooks-lint-history.json`、`findings.md`、`progress.md`、`task_plan.md` 的既有审查改动。
- 所有生产代码变更必须先有对应失败测试或现有测试明确覆盖，再进入实现。

---

### Task 1: 建立布局与后端清理的失败契约

**Files:**
- Modify: `tests/test_capture_index_page.py`
- Modify: `tests/test_module_boundaries.py`
- Modify: `tests/test_application_services.py`
- Modify: `tests/test_storage_boundaries.py`
- Create: `tests/test_workspace_cleanup_contracts.py`

**Interfaces:**
- Consumes: 当前 `pages/a_manage/semantic/index.html`、`manager_base.py`、`application` exports 和 `storage.py`。
- Produces: 明确的新工作台节点契约，以及 `PackBackupService`/重复策略清理契约，供后续任务实现。

- [ ] **Step 1: Write the failing layout contract tests**

在 `CaptureIndexPageTests` 增加以下行为断言：

```python
def test_workspace_uses_overview_sections(self):
    source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
    self.assertIn('class="workspace-header"', source)
    self.assertIn('id="capture-v4-health-detail"', source)
    self.assertIn('class="workspace-content"', source)
    self.assertIn('id="capture-attention-items"', source)
    self.assertIn('id="capture-catalog-panel"', source)

def test_workspace_cache_version_is_polished(self):
    source = (SEMANTIC_PAGE / "index.html").read_text(encoding="utf-8")
    self.assertIn("20260817-workspace-polish-1", source)
```

在 `test_module_boundaries.py` 增加 manager 不再组装 `PackBackupService` 的断言；在 `test_application_services.py` 和新契约测试中断言 application 不再暴露该 facade；在 `test_storage_boundaries.py` 中使用 AST 统计 `storage.py` 的 `is_safe_category_segment`、`resolve_safe_category_dir` 和 `_safe_extension` 各只出现一个定义。

- [ ] **Step 2: Run the focused tests and verify the expected RED state**

Run:

```powershell
python -m unittest tests.test_capture_index_page tests.test_module_boundaries tests.test_application_services tests.test_storage_boundaries tests.test_workspace_cleanup_contracts
```

Expected: FAIL because the new layout classes/IDs/cache version are absent, `PackBackupService` still exists, and the duplicated storage definitions are still present. Do not modify production files until this failure is observed.

- [ ] **Step 3: Add only test helpers needed by the contract**

Keep the AST helper local to `tests/test_workspace_cleanup_contracts.py` and use repository-relative paths. Do not add mocks or new runtime dependencies.

- [ ] **Step 4: Re-run the focused tests to confirm the failure is meaningful**

Run the same focused command and confirm every failure names a missing contract rather than an import or test syntax error.

---

### Task 2: Implement the A-scheme page hierarchy and responsive layout

**Files:**
- Modify: `pages/a_manage/semantic/index.html`
- Modify: `pages/a_manage/semantic/style.css`
- Modify: `tests/test_capture_index_page.py`

**Interfaces:**
- Consumes: Existing behavior IDs including `pack`, transfer controls, v4 metrics, selection controls, pagination, `capture-indexed-items`, `capture-pending-items`, confirmation mask and preview mask.
- Produces: A single responsive layout with `workspace-header`, `capture-v4-health-detail`, `workspace-action-bar`, `workspace-content`, `capture-attention-items` and `capture-catalog-panel` while preserving all old behavior IDs.

- [ ] **Step 1: Re-read the current HTML/CSS and update the test expectation only where the design requires it**

Keep the existing feature-specific IDs. Change only structural assertions in `tests/test_capture_index_page.py` so the test distinguishes visible “attention” and “catalog” sections from the hidden compatibility summary.

- [ ] **Step 2: Run the page contract tests and confirm the new layout assertions remain RED**

Run:

```powershell
python -m unittest tests.test_capture_index_page
```

Expected: the new structure assertions fail against the old page.

- [ ] **Step 3: Rebuild the HTML structure without changing behavior selectors**

In `index.html`:

1. Wrap the title, resource pack selector, refresh, import and export controls in `header.workspace-header`.
2. Keep `capture-transfer-panel` and its file input as an inline secondary panel below the header.
3. Keep `capture-v4-health` as the main health card and add a `capture-v4-health-detail` aside whose values are written by the existing v4 render path.
4. Move reindex progress and selection/index actions into `workspace-action-bar`.
5. Put pending/duplicate cards in `capture-attention-items` before the indexed catalog; retain `capture-pending-items` as the existing render target.
6. Put indexed cards, category filters and pagination inside `capture-catalog-panel`; retain `capture-indexed-items`, `capture-category-filters` and `capture-pagination`.
7. Leave the hidden `capture-summary`, confirmation mask and preview mask in the document.

- [ ] **Step 4: Implement the CSS layout and responsive rules**

In `style.css`:

1. Add semantic variables for surface, border, muted text, accent and danger using the existing palette.
2. Make the header compact and allow the toolbar to wrap without pushing the health card below an excessive empty area.
3. Render the health card as a wide grid with ring, copy, four metric buttons and the new detail list.
4. Render the attention/catalog region as a two-column desktop layout and a single-column mobile layout.
5. Use a 5-column indexed thumbnail grid on wide screens and 3 columns on narrow screens.
6. Keep existing `.summary[hidden]`, `.reindex-progress[hidden]`, focus-visible, reduced-motion and card action rules.

- [ ] **Step 5: Run the page contract and Node syntax checks**

Run:

```powershell
python -m unittest tests.test_capture_index_page
node --check pages/a_manage/semantic/script.js
```

Expected: layout contract passes and JavaScript syntax remains valid.

---

### Task 3: Refactor frontend polling and health state updates without behavior changes

**Files:**
- Modify: `pages/a_manage/semantic/script.js`
- Modify: `tests/test_capture_index_runtime.py`
- Modify: `tests/test_capture_index_page.py`

**Interfaces:**
- Consumes: Existing `pollReindexStatus`, `pollIndexStatus`, `reindexPollTimer`, `reindexPollGeneration`, `indexPollTimer`, `workspaceRequestGeneration` and `renderV4Health` behavior.
- Produces: `createPollingController()` internal helper, shared task button-state updates, and dynamic values for the new v4 health detail nodes.

- [ ] **Step 1: Add a failing runtime contract for the new detail values**

Extend the Node harness fixture so the page contains `capture-v4-health-detail` nodes, then assert a loaded workspace with `v4.complete = 7`, `needs_rebuild = 2`, `pending = 3`, `duplicate = 1` writes those values to the corresponding detail nodes. The assertion must inspect rendered text, not implementation calls.

- [ ] **Step 2: Run the focused runtime harness and verify RED**

Run:

```powershell
python -m unittest tests.test_capture_index_runtime tests.test_capture_index_page
```

Expected: the new detail-value assertion fails because `renderV4Health` does not update the new nodes.

- [ ] **Step 3: Implement the minimal v4 detail rendering**

Add a `v4DetailNodes` map beside `v4MetricNodes` and update both maps from `renderV4Health(v4)`. Keep all values clamped to non-negative numbers and continue using `textContent`.

- [ ] **Step 4: Add a generic polling controller after the detail test is green**

Replace the two pairs of stop/timer/generation state with:

```javascript
function createPollingController() {
  let timer = null;
  let generation = 0;
  return {
    nextGeneration() { generation += 1; return generation; },
    current() { return generation; },
    isCurrent(value) { return value === generation; },
    schedule(callback, delay = 500) {
      timer = window.setTimeout(callback, delay);
    },
    stop() {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
      generation += 1;
    },
  };
}
```

Create one controller for reindex and one for manual index. Adapt both poll functions to call `stop()`, `schedule()` and `isCurrent()` while preserving their current statuses, 500 ms delay, pack checks and completion behavior.

- [ ] **Step 5: Extract shared task button busy-state updates**

Add a small `setTaskBusy(button, busy)` helper that sets `disabled` and `aria-busy` consistently. Use it in reindex and manual index paths only; do not change when buttons are enabled after `error`, `completed` or `completed_with_errors`.

- [ ] **Step 6: Run the complete frontend runtime harness after the refactor**

Run:

```powershell
python -m unittest tests.test_capture_index_runtime tests.test_capture_index_timeout tests.test_capture_index_page
node --check pages/a_manage/semantic/script.js
```

Expected: all existing cross-pack, stale-request, cache, disposal, pagination and polling behaviors pass.

---

### Task 4: Remove dead backend facade/imports and duplicate storage definitions

**Files:**
- Modify: `manager_base.py`
- Modify: `application/services.py`
- Modify: `application/__init__.py`
- Modify: `mixins/web_api.py`
- Modify: `storage.py`
- Delete: `backend/pack_backup.py`
- Modify: `tests/test_application_services.py`
- Modify: `tests/test_module_boundaries.py`
- Modify: `tests/test_pack_boundaries.py`
- Modify: `tests/test_storage_boundaries.py`
- Modify: `tests/test_workspace_cleanup_contracts.py`

**Interfaces:**
- Consumes: Current repository call graph and retained pack transfer/community command paths.
- Produces: No production `PackBackupService`/`backend.pack_backup` references, no unused removed-WebUI imports, and one compatibility definition for each storage policy export.

- [ ] **Step 1: Verify the dead-facade RED contract from Task 1 is still isolated**

Run:

```powershell
python -m unittest tests.test_workspace_cleanup_contracts tests.test_module_boundaries tests.test_application_services
```

Expected: failures only for the still-present facade/export/duplicate definitions.

- [ ] **Step 2: Remove the backup facade and its tests**

Delete `backend/pack_backup.py`. Remove `PackBackupService` from `application/services.py`, `application/__init__.py`, `manager_base.py` and the tests that only instantiate it. Keep `backend/pack_storage.py` runtime backup functions temporarily if repository search shows they are part of any retained compatibility path; the task must not delete underlying functions based only on the absence of the facade.

- [ ] **Step 3: Remove only unused `mixins/web_api.py` imports**

Use repository search after each removal to keep these retained paths intact:

- Keep pack list/detail/export/import functions used by `PackAPIMixin`.
- Keep community install capability used by `mixins/commands.py` through `CommunityPackService`.
- Remove import-only runtime-backup, selection-rule, community-index and old install/uninstall names from `mixins/web_api.py` when no handler/body references them.

- [ ] **Step 4: Collapse the duplicate storage policy definitions**

Delete the earlier local implementations around lines 1290–1350. Keep the later compatibility wrappers that delegate to `infrastructure.storage_policy`, preserving `storage.is_safe_category_segment`, `storage.resolve_safe_category_dir` and `storage._safe_extension` for existing callers.

- [ ] **Step 5: Update boundary tests to assert the new ownership**

Keep security behavior tests unchanged. Add source/AST checks that `storage.py` exports the three compatibility names exactly once and that application/manager code no longer references the deleted backup facade.

- [ ] **Step 6: Run backend-focused tests and imports**

Run:

```powershell
python -m unittest tests.test_application_services tests.test_module_boundaries tests.test_pack_boundaries tests.test_pack_storage_runtime tests.test_pack_storage_security tests.test_storage_boundaries tests.test_workspace_cleanup_contracts
python -m compileall -q application backend infrastructure mixins storage.py manager_base.py
```

Expected: all retained pack transfer, security and storage behavior passes, with no import error for `manager_base` or `application`.

---

### Task 5: Final integration verification and handoff

**Files:**
- Modify: `pages/a_manage/semantic/index.html` (cache-busting version only if not already updated)
- Modify: `tests/test_capture_index_page.py` (expected asset version only if needed)
- Modify: `CHANGELOG.md` only if the final implementation introduces a release note in the current release process

**Interfaces:**
- Consumes: All completed layout, frontend refactor and backend cleanup tasks.
- Produces: Verified working tree with no business-code regressions and an explicit list of changed files.

- [ ] **Step 1: Run the full unittest suite**

Run:

```powershell
python -m unittest discover -s tests
```

Expected: zero failures; record the exact pass/skip count and note any pre-existing asyncio warning separately from test status.

- [ ] **Step 2: Run all static and syntax gates**

Run:

```powershell
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
git diff --check
```

- [ ] **Step 3: Review the diff for scope and stale references**

Run:

```powershell
git diff --stat
rg -n "PackBackupService|backend\.pack_backup|from \.\.backend\.pack_storage import" manager_base.py application mixins tests --glob '*.py'
rg -n "settings/index|catalog/index|资源广场|设置中心|target=\"_top\"|asset_token" pages
```

Confirm only expected audit files remain unrelated dirty changes and no removed page/API is reintroduced.

- [ ] **Step 4: Commit only implementation files if requested by the repository workflow**

Stage the changed page, backend and test files explicitly; do not stage `.brooks-lint-history.json`, `findings.md`, `progress.md` or `task_plan.md` unless the user asks to update audit records in the same commit.

