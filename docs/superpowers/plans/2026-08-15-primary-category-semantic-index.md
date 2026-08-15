# Primary Category and Semantic Index Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将表情包自动选图从“所有标签都可参与路由”重构为“稳定主分类路由 + 最多两个辅助语义标签 + 面向模型的图像语义描述”，修复图片带字但发送时未被考量的问题，并以 v2.1.5 发布。

**Architecture:** 目录条目新增 `primary_category`、`semantic_tags`、`semantic_summary`、`visible_text`、`text_meaning`、`use_cases`、`avoid_cases` 和 `classification_confidence`。自动选图只读取 `primary_category` 建立候选集合；其余字段仅作为候选语义上下文，不参与分类路由。旧 `tags` 字段保留用于 WebUI/兼容读取，但不再决定自动发送分类。旧目录通过确定性迁移获得主分类；无法无歧义迁移的条目标记 `needs_reindex` 并排除自动发送。

**Tech Stack:** Python 3.10+, `unittest`, JSON catalog/index files, existing AstrBot model adapter; no new runtime dependency and no send-time OCR/vector database.

## Global Constraints

- 主分类只能是：`开心`、`悲伤`、`尴尬`、`无奈`、`疑惑`、`震惊`、`愤怒`、`吐槽`、`赞同`、`拒绝`、`卖萌`、`围观`。
- `semantic_tags` 最多 2 个，只用于候选语境提示；不得把它们展开为自动路由分类。
- 必须保留旧 `tags`、旧 `text` 等字段的读取兼容，避免现有 WebUI、资源包和测试崩溃。
- 旧条目迁移优先级固定为：已有合法 `primary_category` > 合法 `category` > 恰好一个主分类旧标签；多义或无法判断则置空并标记 `primary_category_status=needs_reindex`。
- 模型输出不合法时不得猜测到任意主分类；空主分类条目不得进入自动发送候选。
- 索引提示词必须明确整理图片内可见文字、文字含义、适用场景和避免场景；不在发送时临时 OCR。
- 每个任务先写失败测试，再写最小实现；每个任务完成后运行该任务列出的测试。
- 不修改与本重构无关的现有用户改动，不执行 reset/checkout 等破坏性 Git 操作。

---

## Task 1: 建立主分类与辅助语义的规范化边界

**Files:**
- Modify: `backend/tagging.py`
- Test: `tests/test_tagging.py` (create if absent)

- [ ] **1.1 写失败测试：主分类词表、别名和旧上下文标签边界**

  Add tests covering:

  ```python
  self.assertEqual(normalize_primary_category("无奈"), "无奈")
  self.assertEqual(normalize_primary_category("sigh"), "无奈")
  self.assertEqual(normalize_primary_category("嘲讽"), "吐槽")
  self.assertEqual(normalize_primary_category("meow"), "卖萌")
  self.assertIsNone(normalize_primary_category("工作"))
  self.assertIsNone(normalize_primary_category("吃瓜"))
  self.assertEqual(normalize_semantic_tags(["反问", "认错", "额外标签"]), ["反问", "认错"])
  ```

  Run:

  ```text
  python -m unittest tests.test_tagging -v
  ```

  Expected before implementation: import failures for the new helpers.

- [ ] **1.2 实现主分类和语义字段归一化**

  Add `PRIMARY_CATEGORIES`, `MAX_SEMANTIC_TAGS = 2`, `normalize_primary_category(value) -> str | None`, and `normalize_semantic_tags(value) -> list[str]`. Keep `canonical_tag`/`normalize_tags` behavior compatible for legacy callers. Primary-category aliases must be separate from the legacy alias map so `无奈` is not collapsed to the old `无语` tag.

- [ ] **1.3 运行任务测试并更新持久化计划记录**

  Run the task test again and record the result in `progress.md` and `task_plan.md`.

## Task 2: 为目录和索引增加主分类迁移层

**Files:**
- Modify: `storage.py`
- Modify: `infrastructure/selection_state.py`
- Test: `tests/test_tag_lookup_index.py`
- Test: `tests/test_flat_meme_storage.py` or the existing storage test module that covers catalog normalization

- [ ] **2.1 写失败测试：主分类迁移和路由隔离**

  Add cases proving that:

  - a valid `primary_category` wins over all other fields;
  - a valid legacy `category` is migrated;
  - exactly one old primary tag is migrated;
  - ambiguous/no-primary entries become `primary_category=""` with `primary_category_status="needs_reindex"`;
  - an item whose `primary_category` is `尴尬` and whose `semantic_tags` contains `开心` is returned only by the `尴尬` primary lookup.

  Run:

  ```text
  python -m unittest tests.test_tag_lookup_index tests.test_flat_meme_storage -v
  ```

  Expected before implementation: missing primary lookup/migration behavior.

- [ ] **2.2 实现目录条目归一化和确定性迁移**

  Extend `_normalize_catalog_items` with the approved migration order. Normalize new semantic fields, preserve legacy `tags` and `text`, and add an explicit status for unresolved entries. Do not rewrite existing catalog files merely by reading them; normalize on load and persist the new fields when the index is next written.

- [ ] **2.3 建立独立的主分类索引和选择接口**

  Extend the derived index with `by_primary_category`, while retaining `by_tag` for WebUI compatibility. Add an explicit store/selection-state path such as:

  ```python
  pick_indexed_primary_image(
      primary_category: str,
      *,
      candidate_filenames: list[str] | None = None,
      now: float | None = None,
      repeat_window: int | None = None,
  ) -> Path | None
  ```

  It must filter by `primary_category`, ignore unresolved entries, preserve repeat-window behavior, and retain the existing `pick_indexed_image` API for compatibility.

- [ ] **2.4 暴露主分类集合和描述**

  Add primary-category equivalents of `available_categories()` and `category_descriptions()`. Existing methods remain available for old UI paths, but outgoing auto-selection must be able to request the new primary-only methods without depending on secondary tags.

- [ ] **2.5 运行存储与索引回归测试**

  Run the targeted tests from 2.1 plus the existing tag-index tests. Update `findings.md` with the resulting index contract and `progress.md` with the test result.

## Task 3: 重构视觉索引提示词、结果归一化和写入流程

**Files:**
- Modify: `capture.py`
- Modify: `indexing.py`
- Modify: `capture_pipeline.py`
- Modify: `collector.py` if category candidate normalization needs the primary vocabulary
- Test: `tests/test_capture_index_runtime.py`
- Test: `tests/test_capture_pipeline.py`
- Test: `tests/test_primary_semantic_index.py` (create for shared field-contract tests)

- [ ] **3.1 写失败测试：索引结果必须包含图片文字语义**

  Add tests for batch/single normalization asserting:

  ```python
  result["primary_category"] == "尴尬"
  result["semantic_tags"] == ["认错", "反问"]
  result["visible_text"] == "但是不是你自己发的吗"
  result["text_meaning"]
  result["use_cases"]
  result["avoid_cases"]
  result["classification_confidence"]
  result["text"] == result["visible_text"]  # legacy alias
  ```

  Also cover invalid/ambiguous model output producing an empty primary category plus `needs_reindex`.

  Run:

  ```text
  python -m unittest tests.test_primary_semantic_index tests.test_capture_index_runtime tests.test_capture_pipeline -v
  ```

  Expected before implementation: missing fields/version or incompatible normalization.

- [ ] **3.2 更新索引提示词和版本号**

  Replace the 28-tag “自由选择多个标签” contract in batch and single library prompts with the 12 primary categories and the semantic fields. Explicitly instruct the model to transcribe meaningful visible text, explain what that text means in context, and fill `avoid_cases` when the image text conflicts with a response. Bump `LIBRARY_INDEX_VERSION` from 3 to 4 and `LIBRARY_INDEX_PROMPT_VERSION` to a new semantic-primary value so old results are stale.

- [ ] **3.3 实现统一的模型结果归一化**

  Add one normalization path shared by batch and single indexing. It must accept minor legacy keys (`category`, `tags`, `text`) during migration, write the new fields, cap semantic tags at two, preserve the legacy aliases, and never convert arbitrary context tags into a primary category unless the deterministic migration rules allow it.

- [ ] **3.4 让捕获保存主分类而不是所有标签决定分类**

  Update `_catalog_entry_from_vision` and the capture pipeline to write `primary_category` and semantic fields. Keep `tags` as a compatibility projection such as `[primary_category, *semantic_tags]`, but ensure all automatic routing uses the primary field. Scene-category candidates should come from the 12 primary categories, with legacy fake stores/tests falling back safely when the new method is absent.

- [ ] **3.5 验证旧索引重建和新字段写入**

  Run all Task 3 targeted tests. Inspect at least one generated in-memory/catalog entry in the tests to verify visible text and text meaning survive the write/read path. Record any compatibility fallback in `findings.md`.

## Task 4: 将自动选图改为主分类候选 + 语义候选判定

**Files:**
- Modify: `meme_selection.py`
- Modify: `collector.py` only if the outgoing category prompt/normalizer still exposes legacy categories
- Test: `tests/test_meme_selection.py`
- Test: `tests/test_tag_lookup_index.py` if selection/index behavior shares fixtures

- [ ] **4.1 写失败测试：辅助标签不能把图片路由到错误分类**

  Add a regression fixture with `primary_category="尴尬"`, `semantic_tags=["开心"]`, and visible text/meaning describing an awkward self-correction. Assert a `开心` request cannot select it through the primary index, while an `尴尬` request can. Assert the model prompt includes semantic summary, visible text, text meaning, use/avoid cases, and a stable candidate ID.

  Run:

  ```text
  python -m unittest tests.test_meme_selection tests.test_tag_lookup_index -v
  ```

  Expected before implementation: the old tag-based catalog lookup exposes the fixture through the wrong category.

- [ ] **4.2 改造候选构建和分类描述**

  Build outgoing candidates from primary-only catalog entries. Keep the current bounded candidate count and deterministic candidate IDs. Include semantic fields in each candidate record, prioritize entries with meaningful visible text, and tell the model that `avoid_cases` is a hard negative hint. Do not let `semantic_tags` create candidate categories.

- [ ] **4.3 接入主分类选图并保留兼容回退**

  Prefer `pick_indexed_primary_image` and the primary-only catalog methods. For older/fake stores, fall back to the existing methods only when primary fields are unavailable, and filter the returned catalog entries in Python so a secondary tag cannot reintroduce cross-category routing. Preserve the existing exact `candidate_id` selection behavior and random category fallback.

- [ ] **4.4 运行自动选图回归测试**

  Run the Task 4 tests plus the full current meme-selection module. Update `progress.md` and capture the final prompt contract in `findings.md`.

## Task 5: 发布 v2.1.5 并同步文档

**Files:**
- Modify: `metadata.yaml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_release_metadata.py` (create if no release metadata test exists)

- [ ] **5.1 写失败测试：版本和变更记录一致**

  Add a small test asserting metadata and README expose `v2.1.5`, and the changelog contains a dated `v2.1.5` section with the primary-category/semantic-index change.

  Run:

  ```text
  python -m unittest tests.test_release_metadata -v
  ```

  Expected before implementation: current files still report v2.1.4 and lack the release section.

- [ ] **5.2 更新版本、日志和用户可见说明**

  Set the plugin version and badge to `v2.1.5`. Add a dated changelog entry for 2026-08-15 describing primary-only routing, capped semantic tags, image-text semantics, legacy migration, and compatibility behavior. Update the relevant README data-structure/selection description so operators know old ambiguous items require reindexing.

- [ ] **5.3 运行发布元数据测试**

  Run the release test and record the exact output in `progress.md`.

## Task 6: 全量验证和交付检查

**Files:**
- Modify: `task_plan.md`
- Modify: `progress.md`
- Modify: `findings.md`

- [ ] **6.1 运行分层测试**

  Run the focused tests first:

  ```text
  python -m unittest tests.test_tagging tests.test_tag_lookup_index tests.test_flat_meme_storage tests.test_primary_semantic_index tests.test_capture_index_runtime tests.test_capture_pipeline tests.test_meme_selection tests.test_release_metadata -v
  ```

- [ ] **6.2 运行全量静态和单元验证**

  Run:

  ```text
  python -m unittest discover -s tests
  python -m compileall -q .
  python scripts/generate_conf_schema.py --check
  python scripts/check_architecture.py
  git diff --check
  ```

  If the repository has a configured JavaScript check command, run the existing page checks as well; do not introduce a new dependency for this refactor.

- [ ] **6.3 完成记录并交付**

  Mark every completed task in `task_plan.md`, record test counts and any known environmental limitation in `progress.md`, and summarize the final catalog contract and migration behavior in `findings.md`. Before claiming completion, read and follow the verification-before-completion skill and report only checks that actually passed.

## Execution Notes

- Execute this plan inline in the current task because the user explicitly asked to start the refactor. Use the `executing-plans` workflow and keep each task independently testable.
- Do not use `subagent-driven-development` unless a later task is truly independent and can be isolated without sharing the same uncommitted working tree.
- Do not commit over the existing uncommitted compatibility changes. If a commit is needed, isolate only the files belonging to that commit and ask before bundling unrelated user changes.
