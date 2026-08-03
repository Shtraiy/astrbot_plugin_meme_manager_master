# Flat Meme Tag Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将资源包从分类子目录迁移为 `memes/` 平铺图片目录，用稳定的 `meme_<sha256前缀>.<ext>` 文件名和固定规范标签支持多标签索引、筛选与自动发送。

**Architecture:** 新增独立标签规范化模块；`MemeStore` 负责平铺图片、统一 `memes/index.json` 和幂等迁移；旧分类 API 保留函数入口但改为标签兼容层，不再创建分类目录。采集、自动发送、重索引 API 和两个索引页统一消费平铺条目。

**Tech Stack:** Python 3、`unittest`、Quart、现有原子写入工具、原生 JavaScript/CSS、Node `--check`。

## Global Constraints

- 运行时不得新建 `memes/<category>/` 分类目录；所有新图片必须直接写入 `memes/`。
- 规范标签只能来自固定词表，单图最多 5 个，无法归一化的值使用 `其他`。
- 图片 ID 使用内容 SHA-256 前缀；同一内容只保留一张图片并合并标签和富元数据。
- 统一索引写入必须使用原子写入和 pack 级锁；迁移失败时保留源文件和旧索引。
- 重索引不调用模型；未知文件不删除，只统计并跳过。
- 旧 `category` 参数只作为标签别名兼容，不得重新成为目录路径或发送候选维度。
- 每个生产行为变更先写失败测试并观察预期失败，再写最小实现。

---

### Task 1: Add the controlled tag vocabulary

**Files:**
- Create: `backend/tagging.py`
- Create: `tests/test_tagging.py`

**Interfaces:**
- Produces `CANONICAL_TAGS: tuple[str, ...]`.
- Produces `MAX_TAGS = 5`.
- Produces `normalize_tags(value: Any, *, fallback: str = "其他") -> list[str]`.
- Produces `canonical_tag(value: Any) -> str | None`.
- Produces `tag_aliases() -> dict[str, str]`.

- [ ] **Step 1: Write failing normalization tests.**

```python
from backend.tagging import normalize_tags

def test_normalize_tags_maps_aliases_and_deduplicates():
    assert normalize_tags(["生气", "愤怒", "吃惊"]) == ["愤怒", "震惊"]

def test_normalize_tags_limits_results_and_uses_other():
    assert normalize_tags(["愤怒", "震惊", "疑惑", "无语", "嘲讽", "未知长句"]) == [
        "愤怒", "震惊", "疑惑", "无语", "嘲讽"
    ]
    assert normalize_tags(["未知长句"]) == ["其他"]
```

- [ ] **Step 2: Run the focused test and confirm it fails because `backend.tagging` is missing.**

Run: `python -m unittest tests.test_tagging -v`

Expected: import failure for `backend.tagging`.

- [ ] **Step 3: Implement the vocabulary and deterministic normalizer.**

Use the approved canonical set (`开心`, `愤怒`, `悲伤`, `震惊`, `疑惑`, `尴尬`, `害怕`, `期待`, `无语`, `赞同`, `拒绝`, `嘲讽`, `嫌弃`, `感谢`, `道歉`, `安慰`, `催促`, `围观`, `吃瓜`, `摸鱼`, `庆祝`, `工作`, `加班`, `睡觉`, `早安`, `求助`, `发钱`, `其他`) and aliases for existing categories (`happy`, `angry`, `sad`, `surprised`, `confused`, `reply`, `sigh`, `morning`, `sleep`, `work`, `givemoney`, `like`, `see`, `shy`, `fool`, `baka`, `meow`, `cpu`, `color`). Split strings on comma/Chinese punctuation/whitespace, strip backticks and quotes, map aliases, remove duplicates, preserve canonical vocabulary order, and fill `其他` only when no usable tag remains.

- [ ] **Step 4: Run the focused tests and commit the vocabulary.**

Run: `python -m unittest tests.test_tagging -v`

Expected: all tag normalization tests pass.

Commit: `git add backend/tagging.py tests/test_tagging.py && git commit -m "feat: add controlled meme tags"`

### Task 2: Implement the flat `MemeStore` and migration

**Files:**
- Modify: `storage.py:98-631`
- Modify: `tests/test_pack_storage_runtime.py`
- Create: `tests/test_flat_meme_storage.py`

**Interfaces:**
- `MemeStore.save_image(content, tags=None, extension=".png", perceptual_threshold=6) -> SaveResult` writes directly under `memes/`.
- `MemeStore.load_catalog() -> dict` reads `memes/index.json` version 2.
- `MemeStore.write_catalog(entries, metadata=None) -> None` writes the unified index and README.
- `MemeStore.image_paths() -> list[Path]` returns only direct image children of `memes/`.
- `MemeStore.pick_indexed_image(preferred_tags=None, now=None, repeat_window=...) -> Path | None` selects from unified entries.
- `MemeStore.reindex_flat_catalog() -> dict[str, int]` migrates old nested images and returns progress counts.
- Existing category-parameter catalog methods remain only as private migration readers; no public write path creates a category directory.

- [ ] **Step 1: Add failing flat-storage tests.**

```python
import json

from storage import MemeStore


def test_save_image_writes_meme_id_to_flat_directory():
    store = MemeStore(pack_dir)
    result = store.save_image(b"image", ["愤怒", "震惊"], ".png", None)
    assert result.path.parent == store.memes_dir
    assert result.path.name.startswith("meme_")
    assert store.load_catalog()["items"][0]["tags"] == ["愤怒", "震惊"]

def test_reindex_flattens_legacy_category_and_is_idempotent():
    store = MemeStore(pack_dir)
    legacy = store.memes_dir / "happy"
    legacy.mkdir(parents=True)
    (legacy / "happy_0001.png").write_bytes(b"image")
    (legacy / "index.json").write_text(
        json.dumps({"items": [{"filename": "happy_0001.png", "tags": ["生气"]}]}),
        encoding="utf-8",
    )
    first = store.reindex_flat_catalog()
    second = store.reindex_flat_catalog()
    assert first["migrated_file_count"] == 1
    assert second["migrated_file_count"] == 0
    assert list(store.memes_dir.glob("meme_*.png"))
    assert store.load_catalog()["items"][0]["tags"] == ["开心", "愤怒"]
    assert not legacy.exists()
```

- [ ] **Step 2: Run the new tests and confirm they fail on the old category-based contract.**

Run: `python -m unittest tests.test_flat_meme_storage -v`

Expected: failure because `save_image` creates `memes/<category>` and `load_catalog` requires a category.

- [ ] **Step 3: Add flat path and ID helpers.**

Implement `_flat_image_path`, `_meme_id_for_digest`, collision expansion, direct-image scanning, and a version-2 empty catalog. Keep `IMAGE_EXTENSIONS`, atomic writes, digest calculation, and existing perceptual duplicate detection.

- [ ] **Step 4: Implement unified catalog read/write and metadata merge.**

Normalize every entry to include `id`, `filename`, `sha256`, `tags`, `description`, `emotion`, `text`, `indexed`, `send_count`, and `last_sent_at`. Preserve unknown rich fields. `write_catalog` must write `memes/index.json` and `memes/README.md` atomically.

- [ ] **Step 5: Implement flat save, duplicate merge, indexed selection, send markers, and reconcile.**

Use `normalize_tags` at the storage boundary. A duplicate SHA-256 updates the existing entry by tag union and non-empty metadata preference instead of creating another file. `pick_indexed_image` filters by tag overlap when `preferred_tags` is supplied and applies the existing repeat-window weights.

- [ ] **Step 6: Implement the locked migration algorithm.**

Scan direct images and one-level legacy category directories, load old per-category catalogs, merge entries by digest, add mapped legacy category tags, rename through temporary files, write the unified catalog, then remove only managed legacy `index.json`/`README.md` and empty directories. Preserve unknown files and return `processed`, `total`, `migrated_file_count`, `deduplicated_file_count`, `tag_count`, and `skipped_path_count`.

- [ ] **Step 7: Run storage tests, update old tests to the flat contract, and commit.**

Run: `python -m unittest tests.test_tagging tests.test_flat_meme_storage tests.test_pack_storage_runtime -v`

Expected: all focused storage tests pass, including legacy metadata preservation and repeated migration.

Commit: `git add storage.py tests/test_flat_meme_storage.py tests/test_pack_storage_runtime.py && git commit -m "feat: flatten meme storage and migrate catalogs"`

### Task 3: Convert legacy upload and management APIs into tag-compatible operations

**Files:**
- Modify: `backend/models.py`
- Modify: `mixins/emoji_api.py`
- Modify: `mixins/commands.py`
- Modify: `backend/category_manager.py`
- Modify: `tests/test_models_upload_security.py`
- Modify: `tests/test_web_api_behavior.py`
- Create: `tests/test_flat_tag_management.py`

**Interfaces:**
- `scan_emoji_folder()` returns virtual tag buckets backed by unified entries; it never walks or creates category directories.
- `get_emoji_by_category(tag)` treats `category` as a normalized tag alias.
- `add_emoji_to_category(tag, image_file)` uploads with that tag and returns a `meme_` filename.
- Move/copy compatibility functions become remove-tag/add-tag operations; delete functions delete the flat image entry/file by filename.

- [ ] **Step 1: Add failing tests proving upload and tag operations do not create directories.**

```python
def test_legacy_category_upload_creates_flat_meme_and_tag():
    store = MemeStore(memes_dir.parent)
    result = add_emoji_to_category("happy", fake_upload, memes_dir=memes_dir)
    assert result["filename"].startswith("meme_")
    assert not (memes_dir / "happy").exists()
    assert "开心" in MemeStore(memes_dir.parent).load_catalog()["items"][0]["tags"]
```

- [ ] **Step 2: Run focused tests and confirm the current implementation creates `memes/happy`.**

Run: `python -m unittest tests.test_flat_tag_management tests.test_models_upload_security -v`

Expected: failure on the old category path and filename contract.

- [ ] **Step 3: Rewrite upload/list/delete helpers around `MemeStore`.**

Keep filename validation, byte limits, real-image verification, duplicate errors, and pack locks. Normalize the incoming legacy category to a tag. For virtual listing, include a file in every tag bucket it owns. Ensure deletion removes the unified entry and direct image only.

- [ ] **Step 4: Implement tag mutation semantics for old move/copy/clear endpoints.**

Move removes the source tag and adds the target tag; copy adds the target tag without duplicating the file; clear removes a tag from matching entries and uses `其他` if no tag remains. Update API response fields to include `tags` while retaining legacy names for clients.

- [ ] **Step 5: Disable directory-creating category manager mutations.**

Category creation/rename/delete routes must return HTTP 409 with `code: "category_directories_retired"`; none may call `mkdir` for a category. Update command text to use tag terminology and tag counts.

- [ ] **Step 6: Run focused API/security tests and commit.**

Run: `python -m unittest tests.test_flat_tag_management tests.test_models_upload_security tests.test_web_api_behavior -v`

Expected: uploads, deletes, virtual tag listing, and path-security tests pass without nested directory creation.

Commit: `git add backend/models.py mixins/emoji_api.py mixins/commands.py backend/category_manager.py tests/test_flat_tag_management.py tests/test_models_upload_security.py tests/test_web_api_behavior.py && git commit -m "feat: make legacy meme APIs tag based"`

### Task 4: Remove single-category classification from capture and library indexing

**Files:**
- Modify: `capture_pipeline.py`
- Modify: `capture.py:619-690,1119-1465`
- Modify: `collector.py`
- Modify: `tests/test_capture_dispatch_behavior.py`
- Modify: `tests/test_capture_index_api.py`
- Create: `tests/test_capture_flat_tag_index.py`

**Interfaces:**
- Library entry construction becomes `_catalog_entry_from_vision(path, tags, vision, scene) -> dict`.
- Batch scene prompts return normalized `tags`, never a required single `category`.
- `_ensure_library_index` scans `store.image_paths()`, reads one unified catalog, and writes one unified catalog.

- [ ] **Step 1: Add failing capture tests for multi-tag output and flat save.**

```python
def test_capture_entry_keeps_multiple_normalized_tags():
    entry = CaptureMixin._catalog_entry_from_vision(
        Path("meme_deadbeef.png"), ["愤怒", "震惊"],
        {"description": "...", "tags": ["生气", "吃惊"]}, {},
    )
    assert entry["tags"] == ["愤怒", "震惊"]
    assert "category" not in entry
```

- [ ] **Step 2: Run the focused capture tests and confirm the old signature/category requirement fails.**

Run: `python -m unittest tests.test_capture_flat_tag_index tests.test_capture_dispatch_behavior -v`

Expected: failure because the current entry builder and pipeline require a category.

- [ ] **Step 3: Update prompts and parsers to request controlled `tags`.**

Include the canonical vocabulary in library and scene prompts, require at most five short labels, map aliases through `normalize_tags`, and use `其他` when no valid tag is returned. Keep `emotion` and `description` as separate metadata.

- [ ] **Step 4: Update capture pipeline save and duplicate event metadata.**

Pass tags to `MemeStore.save_image`; remove category fallback and category directory assumptions. Duplicate events should store `filename`, `tags`, and `duplicate_of` as a flat `meme_` ID.

- [ ] **Step 5: Rewrite automatic library indexing as one flat scan.**

Build digest/filename maps from `store.load_catalog()`, preserve existing send metadata, call batch/single vision descriptions, normalize returned tags, and write one catalog after the source signature check. Rename the progress message from category to current file/tag batch without changing task state safety.

- [ ] **Step 6: Run capture/index tests and commit.**

Run: `python -m unittest tests.test_capture_flat_tag_index tests.test_capture_dispatch_behavior tests.test_capture_index_api -v`

Expected: capture and background indexing preserve multiple tags and never create category directories.

Commit: `git add capture_pipeline.py capture.py collector.py tests/test_capture_flat_tag_index.py tests/test_capture_dispatch_behavior.py tests/test_capture_index_api.py && git commit -m "feat: classify memes with multiple tags"`

### Task 5: Make automatic sending tag-aware

**Files:**
- Modify: `meme_selection.py`
- Modify: `capture.py` marker parsing and image details
- Modify: `tests/test_explicit_meme_dispatch.py`
- Create: `tests/test_tag_meme_selection.py`

**Interfaces:**
- `MemeSelectionService.choose(..., preferred_tags=None) -> Path | None` replaces category candidate selection.
- `MemeSelectionService.choose_legacy(..., preferred_tags=None) -> Path | None` uses the same flat catalog fallback.
- `MemeStore.pick_indexed_image(preferred_tags=...)` is the final weighted picker.

- [ ] **Step 1: Add failing tests for tag intersection and fallback.**

```python
async def test_choose_prefers_candidate_matching_all_requested_tags():
    selected = await service.choose(event, "请发一个震惊的回复", preferred_tags=["震惊"])
    assert selected.name.startswith("meme_")
    selected_entry = next(
        item for item in store.load_catalog()["items"]
        if item["filename"] == selected.name
    )
    assert "震惊" in selected_entry["tags"]
```

- [ ] **Step 2: Run the focused selection test and confirm the current service only calls `load_catalog(category)`.**

Run: `python -m unittest tests.test_tag_meme_selection tests.test_explicit_meme_dispatch -v`

Expected: failure because the current candidate schema requires a category.

- [ ] **Step 3: Build candidate context from unified entries.**

Limit candidates using configured count, but keep explicit tag requests untruncated. Send `candidate_id`, tags, description, and indexed count to the model. Parse and normalize model-returned tags; accept a candidate ID only if it exists in the catalog.

- [ ] **Step 4: Implement tag scoring and weighted flat selection.**

Score exact tag intersection highest, prefer all requested tags, then partial overlap, then global fallback. Preserve `force_send`, model skip behavior, and repeat-window weighting. Store `last_decision["tags"]` rather than a required category.

- [ ] **Step 5: Convert explicit legacy markers to tag aliases and run tests.**

Run: `python -m unittest tests.test_tag_meme_selection tests.test_explicit_meme_dispatch -v`

Expected: tag hints select matching `meme_` files and legacy markers remain usable.

Commit: `git add meme_selection.py capture.py tests/test_tag_meme_selection.py tests/test_explicit_meme_dispatch.py && git commit -m "feat: select memes by normalized tags"`

### Task 6: Replace capture workspace/reindex API with flat catalog progress

**Files:**
- Modify: `mixins/capture_index_api.py`
- Modify: `mixins/web_routes.py` only if the response schema or route capability changes
- Modify: `tests/test_capture_index_api.py`
- Modify: `tests/test_web_route_capabilities.py`

**Interfaces:**
- `_capture_workspace_for_pack(pack_id, tag="") -> dict` returns `tags`, flat `indexed_items`, flat `pending_items`, and summary counts.
- `_reindex_pack_catalog(pack_id) -> dict[str, int | str]` calls `MemeStore.reindex_flat_catalog()` without model work.
- Progress state keeps `status`, `processed`, `total`, `current_source`, `migrated_file_count`, `deduplicated_file_count`, and `message`.

- [ ] **Step 1: Add failing API tests for flat workspace and tag filter.**

```python
def test_workspace_returns_tags_and_flat_relative_paths():
    workspace = instance._capture_workspace_for_pack("pack", tag="震惊")
    assert workspace["tags"][0]["tag"] == "震惊"
    assert workspace["indexed_items"][0]["relative_path"].startswith("memes/meme_")
    assert "folders" not in workspace
```

- [ ] **Step 2: Run focused API tests and confirm the current response is folder/category based.**

Run: `python -m unittest tests.test_capture_index_api tests.test_web_route_capabilities -v`

Expected: failure on missing `tags` and nested relative paths.

- [ ] **Step 3: Implement unified workspace projection and `tag`/legacy `category` filtering.**

Load one catalog, project each direct image, aggregate tag counts, sort items by capture/index time, and reject invalid tag values through `canonical_tag`. Keep absolute-path redaction.

- [ ] **Step 4: Connect reindex endpoints to the flat migration and progress fields.**

Replace category loops with one `asyncio.to_thread(store.reindex_flat_catalog)` call under `CatalogIndexService.run_locked_pack_mutation`. Return migration and deduplication counts; never invoke a provider.

- [ ] **Step 5: Run focused API tests and commit.**

Run: `python -m unittest tests.test_capture_index_api tests.test_web_route_capabilities -v`

Expected: workspace filtering, progress, path safety, and reindex migration tests pass.

Commit: `git add mixins/capture_index_api.py mixins/web_routes.py tests/test_capture_index_api.py tests/test_web_route_capabilities.py && git commit -m "feat: reindex flat meme catalog"`

### Task 7: Update both index pages to show tags and flat previews

**Files:**
- Modify: `pages/catalog/index.html`, `pages/catalog/script.js`, `pages/catalog/style.css`
- Modify: `pages/a_manage/catalog/index.html`, `pages/a_manage/catalog/script.js`, `pages/a_manage/catalog/style.css`
- Modify: `tests/test_capture_index_page.py`

- [ ] **Step 1: Add failing source-contract tests.**

```python
from pathlib import Path


def test_both_pages_use_tag_filters_and_flat_preview_contract():
    page_sources = [
        Path("pages/catalog/index.html").read_text(encoding="utf-8"),
        Path("pages/catalog/script.js").read_text(encoding="utf-8"),
        Path("pages/a_manage/catalog/index.html").read_text(encoding="utf-8"),
        Path("pages/a_manage/catalog/script.js").read_text(encoding="utf-8"),
    ]
    for source in page_sources:
        assert "capture-tag-filters" in source
        assert "capture-category-filters" not in source
        assert "memes/meme_" in source
        assert "capture-reindex-button" in source
```

- [ ] **Step 2: Run the page tests and confirm the current pages still contain category chips.**

Run: `python -m unittest tests.test_capture_index_page -v`

Expected: failure on the old category-filter contract.

- [ ] **Step 3: Replace folder/category state with tag state in both page copies.**

Render an “全部” chip followed by `response.tags`; request `capture/workspace?tag=<canonical>`. Show tag chips on each card, the flat `meme_` filename, indexed/pending status, description, and migration progress counts.

- [ ] **Step 4: Update preview and reindex actions.**

Build preview requests from `managed_pack_id`, `filename`, and flat `memes/` location only. Keep the existing safe navigation, thumbnail size, error fallback, reindex polling, and disabled-button behavior.

- [ ] **Step 5: Run page tests and JavaScript syntax checks.**

Run: `python -m unittest tests.test_capture_index_page -v`

Run: `node --check pages/catalog/script.js` and `node --check pages/a_manage/catalog/script.js`

Expected: both page copies pass source contracts and parse successfully.

Commit: `git add pages/catalog pages/a_manage/catalog tests/test_capture_index_page.py && git commit -m "feat: browse memes by tags"`

### Task 8: Full regression and completion verification

**Files:**
- Modify only tests or compatibility shims discovered by the verification commands.

- [ ] **Step 1: Run the complete Python suite.**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: exit code 0 and no failing tests.

- [ ] **Step 2: Run both JavaScript syntax checks.**

Run: `node --check pages/catalog/script.js` and `node --check pages/a_manage/catalog/script.js`

Expected: both commands exit 0.

- [ ] **Step 3: Check whitespace, status, and the final diff.**

Run: `git diff --check` and `git status --short`

Expected: no whitespace errors; only planned files are changed or committed.

- [ ] **Step 4: Manually verify the migration contract in a temporary pack.**

Create two legacy category folders containing one duplicate image and one unique image, attach old catalog tags, call `reindex_flat_catalog()`, and verify there are only direct `meme_` files, one merged duplicate entry, canonical tags, no empty category directories, and a second call with zero migration changes.

- [ ] **Step 5: Review the implementation against the design and report evidence.**

Re-read `docs/superpowers/specs/2026-08-03-meme-flat-tag-index-design.md`, map each requirement to a passing test or inspected output, and only then report completion.
