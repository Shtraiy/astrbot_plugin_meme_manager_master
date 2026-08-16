# v4 Health Workspace Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 将 v4 健康度卡真正接入 AstrBot 的表情索引工作台，保留现有缩略图和处置操作，并通过版本/缓存升级让重新安装后加载新页面。

**Architecture:** 后端在 capture/workspace 响应中集中计算完整资源包的 v4 状态，前端只负责把明确的数据契约渲染为健康度面板和可点击筛选。pages/semantic/ 与 pages/a_manage/semantic/ 保持同一份行为契约；普通表情管理页继续保留原有管理职责。

**Tech Stack:** Python 3.10+、unittest、Quart WebUI API、原生 ES modules、CSS、Node --check。

## Global Constraints

- 保留现有缩略图、分页、预览、批量选择、选择索引、全量语义重索引和一键忽略行为。
- v4 完整率分母固定为 complete + needs_rebuild，不把待分类和重复项混入百分比。
- 后端复用 indexing.full_reindex_entry_is_current 的契约判断，不在前端复制 v4 判定逻辑。
- 两份页面副本必须同步更新：pages/semantic/ 与 pages/a_manage/semantic/。
- 动态数据使用 DOM API/textContent；不把 catalog 文件名、标签或模型文本拼接到 innerHTML。
- 版本统一升级到 v2.1.8；静态资源查询参数统一使用 20260816-v4-health-1。
- 不推送远端；实现完成后只创建本地提交，推送需用户单独授权。

---

### Task 1: Add a tested v4 workspace summary contract

Files:
- Modify indexing.py: centralize LIBRARY_INDEX_VERSION = 4 and LIBRARY_INDEX_PROMPT_VERSION = library-semantic-primary-v1 while preserving the names imported by capture.py.
- Modify capture.py: import the centralized constants instead of redefining them.
- Modify mixins/capture_index_api.py: add v4 status calculation and the v4_status workspace filter.
- Test tests/test_capture_index_api.py: add complete/needs-rebuild/pending/duplicate and filter cases.

Interfaces:
- Consumes reconciled catalog entries from MemeStore.reindex_flat_catalog() and existing capture activity events.
- Produces summary.v4 with complete, needs_rebuild, pending, duplicate, checked_total, completion_percent, and status.
- Accepts v4_status values all, complete, needs_rebuild, pending, duplicate.

- [ ] Step 1: Write the failing backend test.

Create four entries after catalog reconciliation:

    complete = {
        "indexed": True,
        "index_version": 4,
        "index_prompt_version": "library-semantic-primary-v1",
        "primary_category": "尴尬",
        "primary_category_status": "ready",
        "semantic_summary": "角色沉默。",
        "visible_text": "",
        "text_meaning": "",
        "use_cases": ["无语"],
        "avoid_cases": [],
        "classification_confidence": 0.94,
        "semantic_tags": ["反应"],
    }
    needs_rebuild = {**complete, "index_version": 3}
    pending = {"indexed": False}
    duplicate = {"indexed": True}

Assert complete=1, needs_rebuild=1, pending=1, duplicate=1, checked_total=2, completion_percent=50. A second request with v4_status=needs_rebuild must return only the stale indexed item.

- [ ] Step 2: Run the focused test and verify the expected failure.

    python -m unittest tests.test_capture_index_api.CaptureIndexApiTests.test_workspace_v4_summary_and_status_filter -v

Expected: FAIL because summary.v4 and the v4_status filter do not exist.

- [ ] Step 3: Implement the minimal backend change.

Add a private classifier in CaptureIndexAPIMixin that uses the refreshed entry SHA and full_reindex_entry_is_current. Exclude filenames represented by an active duplicate event from v4 checked counts, apply v4_status before pagination, preserve the existing summary.indexed/pending/duplicate keys, and return status none, complete, or partial.

- [ ] Step 4: Run the focused API tests.

    python -m unittest tests.test_capture_index_api -v

Expected: all API tests pass.

- [ ] Step 5: Commit the backend contract.

    git add indexing.py capture.py mixins/capture_index_api.py tests/test_capture_index_api.py
    git commit -m "feat: expose v4 workspace health summary"

### Task 2: Add the health panel structure and visual system to both page copies

Files:
- Modify pages/semantic/index.html: add the v4 health panel before the existing toolbar.
- Modify pages/a_manage/semantic/index.html: add the identical panel.
- Modify pages/semantic/style.css: add ring, metric, status and responsive styles.
- Modify pages/a_manage/semantic/style.css: mirror the styles exactly.
- Test tests/test_capture_index_page.py: add structure, cache version and accessibility assertions.

Interfaces:
- Consumes summary.v4 from Task 1.
- Produces stable IDs capture-v4-health, capture-v4-ring-value, capture-v4-health-message, capture-v4-complete, capture-v4-needs-rebuild, capture-v4-pending, capture-v4-duplicate.
- Each metric is a button with a data-v4-filter value.

- [ ] Step 1: Write the failing page-contract test.

For both page directories, assert the HTML contains the health panel IDs, data-v4-filter values, aria-live, style.css?v=20260816-v4-health-1, and script.js?v=20260816-v4-health-1.

- [ ] Step 2: Run the page test and verify it fails.

    python -m unittest tests.test_capture_index_page.CaptureIndexPageTests.test_v4_health_panel_contract_exists_in_both_pages -v

Expected: FAIL because the old four-card summary has no v4 panel IDs.

- [ ] Step 3: Add the semantic HTML and CSS.

Use a panel with one centered ring, a heading/message block, and four metric buttons. The ring uses conic-gradient only for the percentage fill, keeps the number centered, switches to a neutral dash for the empty state, and collapses the metric grid to one column on mobile. Add visible focus-visible styles and reduced-motion support.

- [ ] Step 4: Run the focused page-contract tests.

    python -m unittest tests.test_capture_index_page -v

Expected: the new contract and all existing page tests pass.

- [ ] Step 5: Commit the page structure and styles.

    git add pages/semantic/index.html pages/semantic/style.css pages/a_manage/semantic/index.html pages/a_manage/semantic/style.css tests/test_capture_index_page.py
    git commit -m "feat: add v4 health workspace panel"

### Task 3: Render v4 data and wire status/tag bubble filtering

Files:
- Modify pages/semantic/script.js and pages/a_manage/semantic/script.js: add v4 filter state, health rendering and query propagation.
- Modify mixins/capture_index_api.py: accept v4_status in the workspace endpoint.
- Test tests/test_capture_index_page.py: add runtime assertions for both scripts.
- Test tests/test_capture_index_api.py: assert each v4 filter returns the expected section/count.

Interfaces:
- Consumes summary.v4, v4_status, and the existing category parameter.
- Produces renderV4Health, setV4Filter, and currentV4Filter in both page scripts.

- [ ] Step 1: Write the failing runtime contract test.

Assert both scripts contain renderV4Health, currentV4Filter, params.v4_status = currentV4Filter, button.dataset.v4Filter, and do not use summary.innerHTML.

- [ ] Step 2: Run the runtime test and verify it fails.

    python -m unittest tests.test_capture_index_page.CaptureIndexPageTests.test_v4_health_runtime_contract_exists_in_both_pages -v

Expected: FAIL because the scripts only render the old four-card summary.

- [ ] Step 3: Implement rendering and filtering.

renderV4Health must update the ring, status copy, metric values and active state with DOM APIs. Each metric button sets currentV4Filter, resets currentPage to 1 and reloads the workspace. Existing tag bubbles continue to set selectedCategory and preserve the v4 filter. A pack switch resets both filters.

- [ ] Step 4: Run focused frontend/runtime and API tests.

    python -m unittest tests.test_capture_index_page tests.test_capture_index_runtime tests.test_capture_index_api -v

Expected: all health rendering, filter, thumbnail cache, mutation and API tests pass.

- [ ] Step 5: Commit the interaction layer.

    git add pages/semantic/script.js pages/a_manage/semantic/script.js mixins/capture_index_api.py tests/test_capture_index_page.py tests/test_capture_index_api.py
    git commit -m "feat: wire v4 health filters into capture workspace"

### Task 4: Bump release metadata and prevent stale WebUI assets

Files:
- Modify metadata.yaml: set version v2.1.8.
- Modify main.py: set the @register version to 2.1.8.
- Modify README.md: update the version badge and mention the v4 health workspace.
- Modify CHANGELOG.md: add the v2.1.8 release entry and verification notes.
- Modify tests/test_release_metadata.py: update v2.1.7 assertions to v2.1.8 and retain runtime/manifest consistency coverage.
- Modify both page index.html files: update style and script cache versions to 20260816-v4-health-1.

- [ ] Step 1: Update the release test first.

Change the existing release expectations to v2.1.8 and assert the v4 health panel contract and 20260816-v4-health-1 cache version.

- [ ] Step 2: Run the release test and verify it fails against v2.1.7.

    python -m unittest tests.test_release_metadata -v

Expected: FAIL because the manifest, README badge, CHANGELOG heading and runtime version still say v2.1.7.

- [ ] Step 3: Update metadata, documentation and cache versions.

Keep runtime registration without the v prefix, and keep manifest, README and release heading with the v prefix. Update both page copies to the new asset query parameters.

- [ ] Step 4: Run release and dual-page checks.

    python -m unittest tests.test_release_metadata tests.test_capture_index_page -v

Expected: all metadata, page and cache assertions pass.

- [ ] Step 5: Commit the release surface.

    git add metadata.yaml main.py README.md CHANGELOG.md tests/test_release_metadata.py pages/semantic/index.html pages/a_manage/semantic/index.html
    git commit -m "release: publish v2.1.8 v4 health workspace"

### Task 5: Full verification and local delivery

Files:
- Modify task_plan.md: append implementation progress and final verification.
- Modify progress.md: record test counts, static checks and warnings.
- Modify findings.md: record the resolved stale-UI root cause and final review result.

- [ ] Step 1: Run the complete verification gate.

    python -m unittest discover -s tests
    python -m compileall -q .
    python scripts/generate_conf_schema.py --check
    python scripts/check_architecture.py
    $files = rg --files pages -g '*.js'; foreach ($file in $files) { node --check $file }
    git diff --check

Expected: all tests pass with only the known skipped compatibility test; schema and architecture checks pass; every page JavaScript file parses.

- [ ] Step 2: Verify the installed-page source contract.

Confirm both page copies contain capture-v4-health, the v2.1.8 asset versions, and the existing thumbnail/action controls. Confirm capture/workspace returns summary.v4 in the backend regression test.

- [ ] Step 3: Update the project audit logs.

Record the root cause that the preview existed while production render still used the four-card summary, the v4 panel implementation, final test count and remaining non-blocking warnings in findings.md and progress.md.

- [ ] Step 4: Review the final diff and status.

    git diff --check
    git status --short
    git diff --stat HEAD~4..HEAD

Do not stage the existing .superpowers/brainstorm/ files.

- [ ] Step 5: Leave remote integration to a separate user authorization.

    git log --oneline -5
    git status --short --branch

Leave the branch ahead of origin/main only by the v4 implementation commits. Do not push without fresh explicit authorization for the new commit IDs.

