# Capture Workspace Concurrency and Filtering Implementation Plan

**Goal:** 让全量重索引、人工处置和选择性分类索引异步协作，并提高表情偷取对截图和普通图片的拒绝精度。

**Architecture:** 重索引保留现有后台任务和检查点，但把资源包锁缩短到目录整理、单批结果提交和处置事务；视觉模型调用在锁外，提交前重新读取文件与 catalog，已删除/忽略/变更的项目跳过且不复活。WebUI 复用现有蓝色选择状态，增加选择索引和当前资源包级一键忽略；偷取入口继续共用 CapturePipeline，视觉结果增加内容类型与排除理由并执行高精度硬拒绝。

**Tech Stack:** Python 3.10+, asyncio/Quart, JSON catalog and capture activity files, vanilla JavaScript, unittest/Node syntax checks.

## Global Constraints

- 删除或忽略必须在重索引模型调用期间立即返回，不等待整轮重索引。
- 处置优先：写回前校验文件存在、SHA-256 和活动状态；并发处置项不得被旧索引结果复活。
- 选择索引只处理 `pending` 普通待处理项；`duplicate` 只进入待忽略路径。
- 一键忽略覆盖当前资源包全部 `pending` 与 `duplicate`，不受分类筛选和分页影响，并保留现有黑名单语义。
- 只移除待处理项的批量忽略；已整理项的现有批量删除保持不变。
- 自动偷取和 `/偷取` 使用同一套高精度识别规则；边界图片宁可不入库。
- 两套语义管理页面保持同一行为和缓存版本；不引入外部依赖。

---

### Task 1: Lock the concurrency and strict-capture contracts with failing tests

**Files:**
- Modify: `tests/test_capture_index_api.py`
- Modify: `tests/test_full_reindex.py`
- Modify: `tests/test_collector_requests.py`
- Modify: `tests/test_primary_semantic_index.py`

**Interfaces:**
- Reindex task must not hold `CatalogIndexService`'s pack lock while its injected indexing coroutine is awaiting model work.
- A selected-index request accepts only `pending` filenames and returns a queued task; duplicate selection is rejected or ignored before model work.
- A full-ignore request operates on all pending/duplicate records for the selected pack.
- Strict capture results expose explicit exclusion signals and reject screenshot/UI/document/photo-like results.

- [ ] **Step 1: Add the reindex lock regression test**

  Start a `_run_reindex_task` with an `_ensure_flat_library_index` stub that pauses after entering model work. While paused, invoke `run_locked_pack_mutation` for the same pack and assert it completes before the model stub is released. Keep the existing task state assertions for successful completion.

- [ ] **Step 2: Add selected-index and all-ignore API tests**

  Create a temporary pack containing two pending files and one duplicate activity event. Assert a selected-index request queues only the requested pending filename and that the duplicate is not sent to the indexer. Add a full-ignore request test asserting all pending and duplicate digests are blacklisted/marked ignored regardless of the page or category view.

- [ ] **Step 3: Add strict-capture contract tests**

  Assert `should_skip_meme_result` rejects missing/invalid fields, explicit `is_screenshot`, `is_chat_screenshot`, `is_document`, `is_ui`, and `content_type` values such as `photo`, `screenshot`, `document`, `chat`, or `webpage`, even when the model confidence is high. Assert a clearly described reaction meme with valid fields remains accepted. Assert both single and batch prompts mention the exclusion contract.

- [ ] **Step 4: Run only the new tests and confirm RED**

  Run the focused unittest selectors. Expected failures must be caused by the missing concurrency/API/filter behavior, not test syntax or environment setup.

### Task 2: Split reindex model work from short catalog commits

**Files:**
- Modify: `capture.py`
- Modify: `mixins/capture_index_api.py`
- Modify: `backend/catalog_index_service.py` only if a small helper is required by the existing lock contract

**Interfaces:**
- Add an internal pack-scoped short-write helper used by directory normalization, checkpoints, final catalog commits, and capture workspace mutations.
- Extend the flat index core with an optional selected filename scope while keeping the no-argument background behavior unchanged.
- Reindex commits merge against the latest catalog and filter missing files; they never replace the latest catalog with a stale full snapshot.

- [ ] **Step 1: Remove the outer full-task pack lock**

  Change `_run_reindex_task` to call the progress worker directly. Keep one running task per pack and durable paused/error/completed state, but do not wrap the entire model loop in `run_locked_pack_mutation`.

- [ ] **Step 2: Guard only short mutations**

  Add a helper that runs a synchronous/async catalog mutation through `CatalogIndexService.run_locked_pack_mutation` when available, with the existing `_save_lock` around catalog writes. Use it for `reindex_flat_catalog`, per-batch checkpoints, the final catalog write, disposal, and duplicate-ignore activity changes. Do not call mutating normalization from a signature read.

- [ ] **Step 3: Make commit logic optimistic and merge-based**

  At each checkpoint/final write, reload the current catalog, retain current entries whose files still exist, overlay only model results whose filename and SHA still match the original snapshot, and preserve new entries added after the scan. Treat deleted, ignored, blacklisted, or changed files as concurrent skips; do not restore them. Rebuild derived tag data from the merged catalog through the existing `write_catalog` path.

- [ ] **Step 4: Keep progress/resume semantics intact**

  Continue persisting per-batch checkpoints and `paused` states. Report concurrent skips separately from model errors where the existing state shape allows; a concurrent deletion must not turn a successful user action into a failed disposal.

- [ ] **Step 5: Run concurrency/full-reindex tests and then the existing capture API suite**

  Verify the new lock regression, resumable reindex cases, disposal cases, and timeout cases before proceeding to the UI work.

### Task 3: Add selective indexing and pack-wide ignore APIs

**Files:**
- Modify: `mixins/capture_index_api.py`
- Modify: `mixins/web_routes.py` only if a new route is unavoidable
- Modify: `tests/test_capture_index_api.py`

**Interfaces:**
- Extend `POST capture/index` with an optional validated `items` list containing `{kind: "pending", filename, sha256}`. Without `items`, preserve the existing all-pending behavior.
- Add a pack-wide ignore operation through the existing disposal route or a dedicated `capture/items/ignore-all` route; payload must include only `pack_id` and the server derives all pending/duplicate records from current state.

- [ ] **Step 1: Validate selected pending entries against current state**

  Reject unsafe filenames, duplicate kinds, malformed SHA values, missing files, indexed entries, and stale SHA values. Build the task scope from current catalog data rather than trusting the browser card payload.

- [ ] **Step 2: Queue the scoped index task**

  Reuse the existing `_library_task` state/polling path with a selected filename scope. Preserve the existing conflict with a running full reindex, but allow the new task to use the same short commit path as reindex and disposal.

- [ ] **Step 3: Implement full-pack ignore as one short transaction**

  Under the pack mutation lock, reload catalog/activity, add all pending/duplicate digests to the blacklist, delete ordinary pending files, retain duplicate target files, mark matching activities ignored, and write a catalog that excludes deleted files. Return counts and partial failures using the existing response style.

- [ ] **Step 4: Run focused API tests and inspect serialized responses**

  Verify selected indexing cannot include duplicates, full-ignore is independent of current filter/page, and repeated requests remain idempotent.

### Task 4: Update both semantic management pages

**Files:**
- Modify: `pages/semantic/index.html`
- Modify: `pages/semantic/script.js`
- Modify: `pages/semantic/style.css`
- Modify: `pages/a_manage/semantic/index.html`
- Modify: `pages/a_manage/semantic/script.js`
- Modify: `pages/a_manage/semantic/style.css`
- Modify: `tests/test_capture_index_page.py`
- Modify: `tests/test_capture_index_runtime.py`

**Interfaces:**
- Add a blue-highlighted `选择索引` action that submits selected `pending` cards only.
- Add a confirmed `一键忽略全部待处理和待忽略` action that submits the pack-wide ignore request.
- Keep current blue selection visuals, current-page/current-view selection, clear selection, single-card actions, and indexed-item batch deletion.

- [ ] **Step 1: Extend static page contracts**

  Assert both page copies contain the new select-index and ignore-all controls, retain `card.selected`, and keep existing indexed batch disposal helpers. Update the asset query version in both HTML files.

- [ ] **Step 2: Add selective-index client behavior**

  Filter `selectedItems` to `kind === "pending"`, retain selection for duplicates/indexed items, show a confirmation with the selected count, post filenames and SHA values, poll `capture/index/status`, and refresh while preserving failed/still-selected cards.

- [ ] **Step 3: Remove only pending/duplicate contextual batch ignore**

  Keep `disposalItemsForAction` for indexed batch deletion. For pending/duplicate card buttons, submit only the clicked item even when other pending cards are selected.

- [ ] **Step 4: Add full-ignore-all behavior**

  Confirm the current pack-wide count from workspace summary, post the pack ID to the selected endpoint, clear successful pending/duplicate selections, evict affected thumbnails, and refresh. Keep indexed selections untouched.

- [ ] **Step 5: Run Node harnesses and both page syntax checks**

  Add runtime scenarios for selected pending indexing, duplicate exclusion, pending single-card ignore, indexed batch deletion preservation, and full-ignore confirmation. Run `node --check` for both scripts.

### Task 5: Tighten the capture classifier

**Files:**
- Modify: `collector.py`
- Modify: `capture.py`
- Modify: `capture_pipeline.py`
- Modify: `tests/test_collector_requests.py`
- Modify: `tests/test_primary_semantic_index.py`

**Interfaces:**
- Vision output gains optional `content_type`, `is_screenshot`, `is_chat_screenshot`, `is_document`, `is_ui`, and `rejection_reason` fields.
- `should_skip_meme_result` remains the single acceptance gate used by automatic capture and `/偷取`.

- [ ] **Step 1: Update the single/batch vision prompts**

  Require the model to distinguish reaction meme/sticker from ordinary photo, screenshot, chat transcript, web/UI capture, document, poster/banner, and unrelated image; require explicit boolean exclusion fields and a short reason.

- [ ] **Step 2: Add deterministic high-precision rejection rules**

  Fail closed for invalid structure, explicit exclusion flags, excluded content types, `is_meme=false`, low confidence, or missing meme intent. Preserve accepted reaction images with or without text when the model explicitly identifies a chat-use expression.

- [ ] **Step 3: Keep both capture entry points on the same gate**

  Do not add a manual-command bypass; leave `CapturePipeline` as the shared path and preserve blacklist/dedup behavior after the stricter acceptance decision.

- [ ] **Step 4: Run capture pipeline and classifier regressions**

  Verify screenshots and ordinary photos are returned as `not_meme` before save, valid memes continue through scene classification, and no temporary file/catalog entry is created for rejected images.

### Task 6: Full verification and handoff

**Files:**
- Modify: `CHANGELOG.md`
- Append session notes to existing `progress.md` and `findings.md` only after verification

- [ ] **Step 1: Run focused tests and static checks**

  Run the changed API, full-reindex, capture-pipeline, collector, page contract/runtime tests, both Node checks, `compileall`, schema check, architecture check, and `git diff --check`.

- [ ] **Step 2: Run the full unittest suite**

  Run `python -m unittest discover -s tests -v` and record the exact pass/skip/failure count.

- [ ] **Step 3: Review the final diff**

  Check that no debug artifacts, unrelated generated data, credentials, or accidental page divergence were introduced. Confirm all user-visible behavior from the global constraints is represented in code and tests.

- [ ] **Step 4: Update the changelog and session notes**

  Document concurrent reindex/disposal, selective indexing, full-pack ignore, and stricter capture filtering without changing unrelated release metadata.
