# Full Semantic Reindex Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将表情索引页的“重索引”升级为全目录语义检查：完整 v4 条目跳过视觉模型，旧版/过期/字段不完整条目重新识别，并记录每张图片最近一次手动检查结果。

**Architecture:** 在 `indexing.py` 增加不依赖 provider 的 v4 条目完整性判断，明确检查索引版本、提示词版本、当前 SHA、主分类和语义字段。`CaptureMixin` 将现有 flat library indexing 核心参数化为可处理指定 `MemeStore` 和指定进度状态；后台入口仍执行原有增量行为，手动入口执行全量扫描并在同一 catalog 中写入 `full_reindex_status`/`full_reindex_checked_at`。Web API 继续使用 `capture/reindex` 路由，但任务改为调用语义核心，页面显示跳过、重识别和失败计数。

**Tech Stack:** Python 3.10+, `unittest`/`IsolatedAsyncioTestCase`, JSON catalog/tag index, existing AstrBot vision provider, vanilla module JavaScript; no OCR/vector/new dependency.

## Global Constraints

- 全量检查必须先整理旧分类目录和 flat 文件名，再扫描当前目录中的全部图片。
- 完整条目必须满足：`indexed=true`、`index_version=4`、当前 `index_prompt_version`、当前文件 SHA 相同、合法主分类且非 `needs_reindex`，以及 `semantic_summary`、`visible_text`、`text_meaning`、`use_cases`、`avoid_cases`、`classification_confidence`、`semantic_tags` 字段可归一化。
- 完整 v4 条目不得因插件重启或单纯再次点击而重复调用视觉模型；跳过时写 `full_reindex_status=skipped_current`。
- 成功重新识别写 `full_reindex_status=reindexed`；失败写 `full_reindex_status=error`。无有效当前索引的失败条目必须保持 `indexed=false` 或 `primary_category_status=needs_reindex`，不得进入 `by_primary_category`。
- `full_reindex_checked_at` 使用 Unix 秒时间戳，只描述最近一次手动全量检查，不参与主分类路由。
- 单批失败必须继续逐图补偿；单图失败只增加 `errors`，不能阻塞同一资源包的其他图片。
- 手动全量任务与后台 `capture/index` 互斥，并使用已有资源包锁；源文件集合或内容在写入前变化时放弃本轮写入。
- 保留 `capture/reindex` 和 `capture/reindex/status` 路由，新增状态字段 `skipped`、`reindexed`、`errors`。
- 不删除图片，不引入 OCR、向量数据库或外部运行时依赖；旧 `tags`/`text` 兼容字段继续保留。
- 每个实现任务先写失败测试并确认失败，再写最小实现；不要覆盖与本功能无关的用户修改。

---

## Task 1: 建立 v4 全量检查完整性契约

**Files:**
- Modify: `indexing.py`
- Test: `tests/test_full_reindex.py` (create)

**Interfaces:**
- Produces `full_reindex_entry_is_current(entry: dict, digest: str, *, index_version: int, prompt_version: str) -> bool` for the manual scanner.
- The helper deliberately does not compare `index_provider_id`; a complete v4 semantic record can be skipped when the configured provider changes, while newly reindexed records still record the current provider.

- [x] **1.1 写失败测试：完整 v4 条目可跳过，旧/残缺条目不能跳过**

  Create `tests/test_full_reindex.py` with a focused contract test:

  ```python
  from meme_manager_master.indexing import full_reindex_entry_is_current

  def test_full_reindex_requires_current_v4_sha_primary_and_semantic_fields(self):
      complete = {
          "indexed": True,
          "index_version": 4,
          "index_prompt_version": "library-semantic-primary-v1",
          "index_provider_id": "old-provider",
          "sha256": "a" * 64,
          "primary_category": "尴尬",
          "primary_category_status": "ready",
          "semantic_summary": "承认自己说错话，表情窘迫。",
          "visible_text": "但是不是你自己发的吗",
          "text_meaning": "带自嘲的反问。",
          "use_cases": ["承认口误"],
          "avoid_cases": ["真诚赞同"],
          "classification_confidence": 0.92,
          "semantic_tags": ["认错"],
      }
      self.assertTrue(full_reindex_entry_is_current(
          complete, "a" * 64,
          index_version=4,
          prompt_version="library-semantic-primary-v1",
      ))
      self.assertFalse(full_reindex_entry_is_current(
          {**complete, "index_version": 3}, "a" * 64,
          index_version=4,
          prompt_version="library-semantic-primary-v1",
      ))
      self.assertFalse(full_reindex_entry_is_current(
          {key: value for key, value in complete.items() if key != "text_meaning"},
          "a" * 64,
          index_version=4,
          prompt_version="library-semantic-primary-v1",
      ))
      self.assertFalse(full_reindex_entry_is_current(
          {**complete, "primary_category": "工作"}, "a" * 64,
          index_version=4,
          prompt_version="library-semantic-primary-v1",
      ))
  ```

  Run:

  ```text
  python -m unittest tests.test_full_reindex.FullReindexContractTests.test_full_reindex_requires_current_v4_sha_primary_and_semantic_fields -v
  ```

  Expected before implementation: import failure because the helper does not exist.

- [x] **1.2 实现完整性判断函数**

  Add `full_reindex_entry_is_current` to `indexing.py`. Require `indexed` truthy, exact version/prompt/SHA, `normalize_primary_category(primary_category)` truthy, `primary_category_status != "needs_reindex"`, and all seven semantic keys. Accept empty `visible_text`, `text_meaning`, `use_cases`, `avoid_cases`, or `semantic_tags` as valid normalized values, but require `semantic_summary` to be a non-empty string and `classification_confidence` to be a numeric value in `[0, 1]`. Use existing `normalize_semantic_tags` and text-list-compatible type checks; do not mutate the entry.

- [x] **1.3 运行契约测试并记录结果**

  Run the focused test again and update `progress.md` with the red/green result. Do not change the background `_catalog_entry_is_current` provider behavior in this task.

## Task 2: 将现有语义索引核心参数化为手动全量扫描

**Files:**
- Modify: `capture.py`
- Test: `tests/test_full_reindex.py`
- Test: `tests/test_capture_index_timeout.py` if the signature change requires timeout fixture updates

**Interfaces:**
- Extends `_ensure_flat_library_index` with keyword-only parameters `target_store: MemeStore | None = None`, `progress_state: dict | None = None`, and `full_reindex: bool = False`; the no-argument call remains the existing background incremental path.
- Produces per-item markers `full_reindex_status` and `full_reindex_checked_at` in the unified catalog.
- Produces progress counters `processed`, `total`, `skipped`, `reindexed`, `errors`, and legacy-compatible `classified`.

- [x] **2.1 写失败测试：完整项跳过并写标记**

  Add an async test that creates a temporary `MemeStore`, writes one image and a complete v4 catalog entry, constructs a minimal `CaptureMixin` instance with real `asyncio.Lock` objects and a provider id, and calls:

  ```python
  await instance._ensure_flat_library_index(
      target_store=store,
      progress_state=state,
      full_reindex=True,
  )
  ```

  Replace `_describe_library_batch` and `_describe_library_single` with async callables that fail the test if invoked. Assert the catalog entry receives `full_reindex_status == "skipped_current"`, a positive `full_reindex_checked_at`, and state values `processed=1`, `skipped=1`, `reindexed=0`, `errors=0`, `status="completed"`.

  Run:

  ```text
  python -m unittest tests.test_full_reindex.FullReindexRuntimeTests.test_complete_v4_entry_is_skipped_and_marked -v
  ```

  Expected before implementation: `_ensure_flat_library_index` rejects the new keyword arguments or does not write the marker.

- [x] **2.2 实现可指定 store/state 的扫描入口**

  At the start of `_ensure_flat_library_index`, bind `store = target_store or self.store` and `state = progress_state or self._library_index_state`. Replace internal catalog/image/state references with these locals while preserving the no-argument background behavior. Keep the existing `_library_lock` and `_save_lock` semantics.

- [x] **2.3 写失败测试：旧版、SHA 变化和字段不完整条目会调用模型**

  Add an async test with three files: one `index_version=3`, one current metadata with a changed SHA, and one v4 entry missing `avoid_cases`. Make the fake batch result return valid normalized data for all three and assert the model callback receives all three paths, every resulting entry has `full_reindex_status == "reindexed"`, and state reports `reindexed=3`, `skipped=0`, `errors=0`.

- [x] **2.4 实现全量 skip/reindex 分流和成功标记**

  In `full_reindex=True` mode, use `full_reindex_entry_is_current` with the current file digest. Copy complete entries into `records` without model calls and write `skipped_current`; send every other path through the existing batch/逐图 flow. On a valid model result, merge stable send counters, current digest/perceptual hash, current v4 metadata, normalized semantic fields, and `reindexed` marker. Keep the existing incremental mode’s current-entry check unchanged except for using the local `store`/`state`.

- [x] **2.5 写失败测试：批量和逐图失败只标记单图并继续收尾**

  Add an async test with one stale image whose batch and single callbacks raise. Assert the task reaches `completed_with_errors`, `processed=1`, `errors=1`, writes `full_reindex_status == "error"`, `indexed is False`, `primary_category_status == "needs_reindex"`, and the rebuilt `tag_index.json` has no entry for that image under `by_primary_category`. Also assert no exception escapes the task.

- [x] **2.6 实现失败保留策略、源签名保护和最终计数**

  For full-mode failures, preserve send statistics and harmless legacy fields but force `indexed=False` and `primary_category_status="needs_reindex"` when the current content has no valid reindexed result. Do not let an incomplete model response count as `reindexed`. Unlike the old incremental early-return path, continue processing the rest of a failed batch. Before writing, compare the source signature collected from the target store; on mismatch skip the write and set an error message. Write the catalog once with `classification_index_complete` based on all current entries, allowing `write_catalog` to rebuild `tag_index.json`/`by_primary_category`.

- [x] **2.7 运行核心回归测试**

  Run:

  ```text
  python -m unittest tests.test_full_reindex tests.test_capture_index_timeout -v
  ```

  Record counts in `progress.md`; existing background indexing tests must remain green.

- [x] **2.8 补充无视觉模型时的幂等跳过保护**

  完整 v4 条目在未配置视觉模型时仍可写入 `skipped_current` 并正常完成；只有存在待重新识别条目时才进入 blocked 状态。

## Task 3: 让 `capture/reindex` API 驱动全量语义任务并互斥

**Files:**
- Modify: `mixins/capture_index_api.py`
- Modify: `mixins/web_routes.py`
- Test: `tests/test_capture_index_api.py`
- Test: `tests/test_web_route_registry.py` if route description assertions exist

**Interfaces:**
- `_reindex_pack_catalog_with_progress(pack_id, state)` delegates to the actual plugin’s `_ensure_flat_library_index(target_store=MemeStore(pack_dir), progress_state=state, full_reindex=True)` and returns the catalog migration plus semantic counters.
- `_api_capture_reindex_status` returns defaults for `skipped`, `reindexed`, and `errors` even before the first task.

- [x] **3.1 写失败测试：API 状态暴露全量计数**

  Extend `ReindexProgressApiTests` so the fake semantic core updates the supplied state with `skipped=1`, `reindexed=1`, and `errors=0`. After the task finishes, assert the API response contains all three counters, `processed == total`, and a completion message describing skip/reindex counts. Add an idle-status assertion for zero-valued counters.

  Run:

  ```text
  python -m unittest tests.test_capture_index_api.ReindexProgressApiTests -v
  ```

  Expected before implementation: the route only reports file rename counts and omits the new counters/message.

- [x] **3.2 接入全量核心并初始化状态**

  Keep `_reindex_pack_catalog` as a direct filesystem-only compatibility helper for callers that use it explicitly, but make the async task path call the semantic core. Extend `_new_reindex_state` with zero-valued `skipped`, `reindexed`, `errors`, and `classified`. Update `_run_reindex_task` to emit `completed` or `completed_with_errors` and a message such as `全量语义重索引完成：跳过 X 张，重新识别 Y 张，失败 Z 张；整理 N 个文件名`.

- [x] **3.3 写失败测试：手动全量和待分类索引互斥**

  Add API tests proving `_api_capture_index` returns 409 while any reindex task is running, and `_api_capture_reindex` returns 409 while `_library_task` is running. Keep the existing same-pack duplicate-task rejection test.

- [x] **3.4 实现任务互斥和状态默认值**

  Reject `capture/index` when any `_reindex_tasks` task is active, and reject `capture/reindex` when `_library_task` is active or any other full reindex task is active. Return status snapshots without scanning the workspace. Update the route description from filesystem-only wording to `手动全量语义重索引表情包`.

- [x] **3.5 运行 API 和路由回归测试**

  Run:

  ```text
  python -m unittest tests.test_capture_index_api tests.test_web_route_registry -v
  ```

## Task 4: 更新两个语义索引页面的确认、进度和互斥提示

**Files:**
- Modify: `pages/semantic/index.html`
- Modify: `pages/semantic/script.js`
- Modify: `pages/a_manage/semantic/index.html`
- Modify: `pages/a_manage/semantic/script.js`
- Test: `tests/test_capture_index_page.py`
- Test: `tests/test_capture_index_runtime.py`

**Interfaces:**
- Both page copies retain the same route IDs and polling endpoints.
- `renderReindexProgress(state)` shows `processed/total` plus `skipped`, `reindexed`, and `errors` without injecting HTML.
- Terminal states are `completed` and `completed_with_errors`; only `error` is an API-level fatal failure.

- [x] **4.1 写失败测试：页面文案和计数契约**

  Extend page tests to require `全量语义重索引`, text explaining that complete v4 entries are skipped and old entries call the vision model, and script literals for `skipped`, `reindexed`, `errors`, and `completed_with_errors`. Extend the Node harness assertion to feed a completed state and verify the progress label contains the three counts.

  Run:

  ```text
  python -m unittest tests.test_capture_index_page tests.test_capture_index_runtime -v
  ```

  Expected before implementation: current pages still say “重索引只整理文件编号，不重复识别” and only show the processed fraction.

- [x] **4.2 更新 HTML 文案和缓存版本**

  Change both subtitles to explain that full reindex scans the directory and skips complete v4 entries. Change the button to `全量语义重索引`; keep `capture/index` as `分类索引待处理项`. Update the embedded confirmation text and page script cache-buster so old browsers load the new behavior.

- [x] **4.3 实现计数渲染、完成态和按钮互斥**

  Append `跳过 X · 重识别 Y · 失败 Z` to the progress label using `textContent`. Poll until `completed`, `completed_with_errors`, or `error`; refresh workspace after either successful terminal state, clear thumbnail cache after an actual task, and keep the button disabled while either index task is active. Preserve generation guards, confirmation dialog, and no-`innerHTML` rendering.

- [x] **4.4 运行两页静态与 Node 回归测试**

  Run:

  ```text
  python -m unittest tests.test_capture_index_page tests.test_capture_index_runtime -v
  node --check pages/semantic/script.js
  node --check pages/a_manage/semantic/script.js
  ```

## Task 5: 发布 v2.1.6、更新日志并完成全量验证

**Files:**
- Modify: `metadata.yaml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_release_metadata.py`
- Modify: `progress.md`
- Modify: `findings.md`
- Modify: `task_plan.md`

- [x] **5.1 写失败测试：发布元数据指向 v2.1.6**

  Change the release test expectation from v2.1.5 to v2.1.6 and require a changelog phrase covering full semantic reindex, v4 skip, and per-image markers. Run:

  ```text
  python -m unittest tests.test_release_metadata -v
  ```

  Expected before implementation: metadata, README badge, and changelog still describe v2.1.5.

- [x] **5.2 更新版本、CHANGELOG 和操作说明**

  Set `metadata.yaml` and the README badge to v2.1.6. Add a dated `## [v2.1.6] - 2026-08-15` entry describing the full-directory scan, complete-v4 skip behavior, legacy semantic reindexing, markers, failure isolation, and old-directory flattening. Mention in the README that the page’s full semantic reindex is the manual migration path for old packs.

- [x] **5.3 运行分层和全量验证**

  Run focused tests:

  ```text
  python -m unittest tests.test_full_reindex tests.test_capture_index_api tests.test_capture_index_page tests.test_capture_index_runtime tests.test_release_metadata -v
  ```

  Then run the full gates:

  ```text
  python -m unittest discover -s tests
  python -m compileall -q .
  python scripts/generate_conf_schema.py --check
  python scripts/check_architecture.py
  node --check pages/semantic/script.js
  node --check pages/a_manage/semantic/script.js
  git diff --check
  ```

- [x] **5.4 更新工作记录并提交实现**

  Record exact test counts and any environmental limitation in `progress.md`, summarize the final marker/index contract in `findings.md`, and mark this feature’s phases in `task_plan.md`. Review the final diff, stage only feature files, and create a focused commit after fresh verification; do not push until the user explicitly requests it.

## Execution Notes

- Execute inline in the current `main` workspace because the user explicitly declined a worktree.
- Use the `executing-plans` workflow with task checkpoints and the TDD red/green cycle in every task.
- Use the verification-before-completion skill before saying the feature is complete or any gate passes.
- Request a code review after the major feature is implemented and before offering merge/push actions.
