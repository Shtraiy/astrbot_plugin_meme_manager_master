# 表情模型配置与重索引工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除重复的回复情景模型配置，并为表情索引页增加无模型重索引、分类筛选、缩略图和上下布局。

**Architecture:** 复用 `MemeStore.renumber_category()` 的临时文件重命名机制，新增 catalog 引用同步方法并由 pack-scoped API 锁保护。两套静态索引页面共享相同的数据契约和交互行为，但保留各自相对资源路径；页面分类筛选通过 `capture/workspace?category=` 获取指定分类完整列表。

**Tech Stack:** Python 3、Quart Web API、原生 JavaScript、CSS、unittest、Node `--check`。

## Global Constraints

- 重索引只修改文件名、catalog 的 `filename`/`id`，不得调用模型或改变已有索引元数据。
- `reply_scene_provider_id` 不再出现在运行时配置或生成的 schema 中；回复情景选择使用 `scene_provider_id`。
- 图片预览只使用现有 `meme_image_data` API 返回的 Data URL。
- 两套索引页面 `pages/semantic` 与 `pages/a_manage/semantic` 必须保持功能一致。
- 不自动提交 Git；保留工作区中已有的 `README_STYLE.md` 删除和此前正文保护修复。

---

### Task 1: Remove the redundant reply-scene provider

**Files:**
- Modify: `_conf_schema.json`
- Modify: `runtime_config.py`
- Modify: `meme_selection.py`
- Modify: `CONFIGURATION.md`
- Test: `tests/test_runtime_config.py`

- [x] Add failing assertions that the typed config and schema omit `reply_scene_provider_id`.
- [x] Remove the field and legacy path from runtime config and regenerate/check `_conf_schema.json`.
- [x] Make both selection paths use `scene_provider_id` directly.
- [x] Update configuration documentation and run focused tests.

### Task 2: Add catalog-safe reindexing

**Files:**
- Modify: `storage.py`
- Modify: `mixins/capture_index_api.py`
- Modify: `mixins/web_routes.py`
- Test: `tests/test_pack_storage_runtime.py`
- Test: `tests/test_capture_index_api.py`

- [x] Add a failing storage test with a missing sequence number and an indexed catalog entry whose metadata must survive.
- [x] Implement `MemeStore.reindex_category()` and `MemeStore.reindex_all_categories()` using existing temporary renames and catalog writes.
- [x] Add `capture/reindex` POST route using the selected pack and `CatalogIndexService.run_locked_pack_mutation()`.
- [x] Return changed-file/category counts and ensure failures return an actionable response.
- [x] Run focused storage/API tests.

### Task 3: Update the index page data contract

**Files:**
- Modify: `mixins/capture_index_api.py`
- Test: `tests/test_capture_index_api.py`

- [x] Add a failing category-filter test.
- [x] Accept an optional `category` query parameter, preserve all folder summary chips, and return the selected category's complete item lists.
- [x] Keep the existing 48-item cap for the unfiltered overview to avoid changing initial page cost.
- [x] Run API tests.

### Task 4: Rebuild both index page layouts

**Files:**
- Modify: `pages/semantic/index.html`, `pages/semantic/script.js`, `pages/semantic/style.css`
- Modify: `pages/a_manage/semantic/index.html`, `pages/a_manage/semantic/script.js`, `pages/a_manage/semantic/style.css`
- Test: `tests/test_capture_index_page.py`, `tests/test_indexed_emoji_thumbnail_cards.py`

- [x] Add failing source-contract assertions for the reindex button, category filter, vertical sections, and thumbnail preview behavior in both page copies.
- [x] Add the reindex action with confirmation and status feedback.
- [x] Render an “全部” chip plus category chips; reload the workspace with the selected category.
- [x] Render indexed items above pending items and preserve thumbnail loading/error/retry behavior.
- [x] Add responsive CSS for stacked sections and thumbnail cards.
- [x] Run focused Python tests and both Node syntax checks.

### Task 5: Full verification

- [x] Run `python -m unittest discover -s tests -p "test_*.py" -v`.
- [x] Run `node --check pages/semantic/script.js` and `node --check pages/a_manage/semantic/script.js`.
- [x] Run `git diff --check` and inspect the final changed-file list.
