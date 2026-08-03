# Meme Multi-Tag Lookup Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Raise the fixed-tag limit to six, merge duplicate images into one flat file with the union of tags, and maintain a recoverable tag lookup index for fast Bot selection.

**Architecture:** \`memes/index.json\` remains the source of truth for complete image metadata. \`MemeStore\` derives \`memes/tag_index.json\` from the normalized catalog after every catalog write, while Bot selection reads the derived index and falls back to rebuilding from the catalog. The capture pipeline always classifies an image before saving so duplicate uploads can merge current classification tags.

**Tech Stack:** Python 3, \`unittest\`, pathlib, atomic JSON writes, existing Pillow-based optional perceptual hashing.

## Global Constraints

- Use the existing fixed canonical tag vocabulary; do not add custom tags.
- A single image must have one physical file and at most 6 normalized tags.
- \`memes/index.json\` is authoritative; \`memes/tag_index.json\` is derived and rebuildable.
- Preserve existing exact SHA-256 and optional perceptual duplicate behavior.
- Preserve current WebUI virtual tag-bucket semantics and Bot repeat-window weighting.
- Do not discard unrelated existing working-tree changes.

---

### Task 1: Add red tests for six tags and duplicate tag merging

**Files:**
- Modify: \`tests/test_tagging.py\`
- Modify: \`tests/test_flat_meme_storage.py\`
- Modify: \`tests/test_pack_storage_runtime.py\`

**Interfaces:**
- Consumes: \`normalize_tags\`, \`MemeStore.save_image\`, and \`MemeStore.load_catalog\`.
- Produces: regression cases that fail while \`MAX_TAGS\` remains 5 or duplicate merging is incomplete.

- [ ] **Step 1: Write the failing tests**

Add a seven-tag normalization test asserting the deterministic first six tags. Add a storage test that saves identical bytes with two different tags and asserts one physical image, one catalog item, and the union of both tags. Add a duplicate-save test that preserves existing non-empty catalog metadata while adding a new tag.

- [ ] **Step 2: Run the focused tests to verify failure**

\`\`\`powershell
python -m unittest tests.test_tagging tests.test_flat_meme_storage tests.test_pack_storage_runtime -v
\`\`\`

Expected: the seven-tag test fails because the result is capped at five; metadata/tag assertions fail if the duplicate path does not merge the supplied data.

### Task 2: Add red tests for the derived tag index and recovery

**Files:**
- Create: \`tests/test_tag_lookup_index.py\`

**Interfaces:**
- Consumes: \`MemeStore.save_image\`, \`MemeStore.write_catalog\`, \`MemeStore.pick_indexed_image\`, and \`memes/tag_index.json\`.
- Produces: tests for index shape, multi-tag deduplication, mutation rebuilds, and fallback recovery.

- [ ] **Step 1: Write the failing tests**

Create two tagged indexed images, read \`tag_index.json\`, and assert each tag bucket points to the same meme ID while \`items\` contains that ID once. Remove or corrupt the lookup file, call \`pick_indexed_image(\"happy\")\`, and assert the image is returned and the lookup file is recreated. Assert unindexed items remain in \`index.json\` but are excluded from Bot candidates.

- [ ] **Step 2: Run the new module to verify failure**

\`\`\`powershell
python -m unittest tests.test_tag_lookup_index -v
\`\`\`

Expected: failure because the lookup file and lookup-backed selection path do not yet exist.

### Task 3: Implement six-tag normalization and lookup primitives

**Files:**
- Modify: \`backend/tagging.py:40,123-132\`
- Modify: \`storage.py\` catalog read/write and selection methods

**Interfaces:**
- Consumes: red tests from Tasks 1 and 2.
- Produces: \`MAX_TAGS = 6\`, a lookup path, a catalog-to-lookup builder, an atomic writer, and a validated reader/rebuilder.

- [ ] **Step 1: Change only the tag cap**

Set \`MAX_TAGS = 6\`, update the normalization docstring, and run \`python -m unittest tests.test_tagging -v\`; all tagging tests must pass.

- [ ] **Step 2: Implement the lookup builder**

Build a versioned structure containing \`source_updated_at\`, \`by_tag\`, and one \`items\` record per meme ID. Include only existing supported image files with \`indexed\` truthy. Sort IDs and tag buckets for deterministic output. Write it atomically through the existing helper.

- [ ] **Step 3: Synchronize after every catalog write**

Call the builder after \`write_catalog()\` writes normalized \`index.json\`. Keep the lookup derived, never authoritative, and ensure legacy category-shaped writes use this same path.

- [ ] **Step 4: Add validation and recovery**

Validate lookup version, source timestamp, IDs, filenames, tags, and file existence. If validation fails or the file is absent, rebuild from the authoritative catalog and use the rebuilt data immediately.

- [ ] **Step 5: Run focused tests**

\`\`\`powershell
python -m unittest tests.test_tagging tests.test_flat_meme_storage tests.test_pack_storage_runtime tests.test_tag_lookup_index -v
\`\`\`

Expected: all focused tests pass.

### Task 4: Switch Bot selection to the derived index

**Files:**
- Modify: \`storage.py:257-287\`
- Modify: \`tests/test_tag_lookup_index.py\`

**Interfaces:**
- Consumes: the lookup reader from Task 3.
- Produces: \`pick_indexed_image()\` using tag buckets while preserving send-count and repeat-window weighting.

- [ ] **Step 1: Add selection-specific assertions**

Create two indexed images under different tags and assert selecting \`\"happy\"\` never returns the image lacking \`\"开心\"\`. Add a multi-tag case asserting an image carrying two requested tags is considered once.

- [ ] **Step 2: Run the assertions before implementation**

\`\`\`powershell
python -m unittest tests.test_tag_lookup_index -v
\`\`\`

Expected: the assertions fail or exercise the old full-catalog path before the selection switch.

- [ ] **Step 3: Implement candidate lookup**

Collect a set of candidate IDs from \`by_tag\`, resolve compact item records to flat paths, filter missing/unsupported/unindexed entries, and apply the existing \`_send_weight()\` values. With no preferred tag, union all lookup item IDs.

- [ ] **Step 4: Run selection and API tests**

\`\`\`powershell
python -m unittest tests.test_tag_lookup_index tests.test_capture_index_api tests.test_web_api_behavior -v
\`\`\`

Expected: all pass with unchanged tag filtering semantics.

### Task 5: Merge current capture labels for duplicate images

**Files:**
- Modify: \`capture_pipeline.py:108-135,228-275\`
- Modify: \`storage.py\` duplicate merge helper if metadata must pass through
- Create or modify: \`tests/test_capture_pipeline.py\`

**Interfaces:**
- Consumes: normalized scene/vision tags and \`MemeStore.save_image\`.
- Produces: duplicate capture results that merge current tags and useful metadata while retaining \`duplicate\` status and activity logging.

- [ ] **Step 1: Write the failing integration test**

Seed a store with image bytes tagged \`\"开心\"\`, run the capture save path with the same bytes classified as \`\"嘲讽\"\`, and assert the result remains \`duplicate\`, the image count remains one, and the catalog contains both tags.

- [ ] **Step 2: Run the test to verify failure**

\`\`\`powershell
python -m unittest tests.test_capture_pipeline -v
\`\`\`

Expected: failure because the current early duplicate branch bypasses classification/merge.

- [ ] **Step 3: Move duplicate detection after classification**

Keep image loading and safety checks first, perform vision and scene classification, normalize \`[category, scene.tags, vision.tags]\`, then call \`save_image()\`. Remove the pre-classification early return that prevents new tags from reaching storage. Preserve status reporting and duplicate event fields.

- [ ] **Step 4: Preserve non-empty metadata on duplicate saves**

Merge current catalog metadata without overwriting existing non-empty description, emotion, text, indexed state, or send statistics. Keep the existing saved path as a pending entry for later indexing.

- [ ] **Step 5: Run capture-focused tests**

\`\`\`powershell
python -m unittest tests.test_capture_activity tests.test_capture_pipeline tests.test_capture_index_api -v
\`\`\`

Expected: all pass, with duplicate events still recorded.

### Task 6: Rebuild lookup during migration and mutations

**Files:**
- Modify: \`storage.py:646-761\`
- Modify: \`backend/models.py\` mutation helpers if any path bypasses \`write_catalog()\`
- Modify: \`tests/test_flat_meme_storage.py\`, \`tests/test_flat_tag_management.py\`

**Interfaces:**
- Consumes: lookup writer and validator from Task 3.
- Produces: idempotent migration and WebUI tag mutations with no stale lookup IDs.

- [ ] **Step 1: Add migration/mutation assertions**

Assert migration creates a correct lookup after cross-category duplicate migration, and copy, move, clear-category, and delete operations remove or update IDs in the derived file.

- [ ] **Step 2: Run the tests to verify failure**

\`\`\`powershell
python -m unittest tests.test_flat_meme_storage tests.test_flat_tag_management -v
\`\`\`

Expected: lookup assertions fail until all mutation paths write through the synchronizer.

- [ ] **Step 3: Route mutations through the synchronizer**

Use \`write_catalog()\` for migration and model helpers. Add a public lightweight \`rebuild_tag_index()\` only if an explicit repair call is needed; it must read the authoritative catalog and write only the derived file.

- [ ] **Step 4: Run migration and management tests**

\`\`\`powershell
python -m unittest tests.test_flat_meme_storage tests.test_flat_tag_management tests.test_pack_storage_runtime -v
\`\`\`

Expected: all pass and repeated migration remains idempotent.

### Task 7: Full verification and documentation

**Files:**
- Modify: \`INDEX_AND_DEDUPE.md\` if the storage contract needs updating
- Modify: \`CHANGELOG.md\` with the user-visible behavior change

**Interfaces:**
- Consumes: implementation and regression tests from Tasks 1-6.
- Produces: verified feature and updated storage documentation.

- [ ] **Step 1: Run the full Python test suite**

\`\`\`powershell
python -m unittest discover -s tests -v
\`\`\`

Expected: all tests pass, with only pre-existing optional skips.

- [ ] **Step 2: Run syntax and whitespace checks**

\`\`\`powershell
node --check pages/semantic/script.js
node --check pages/a_manage/semantic/script.js
git diff --check
\`\`\`

Expected: all commands exit successfully.

- [ ] **Step 3: Update documentation after behavior is verified**

Document the single-file/multi-tag rule, six-tag cap, \`index.json\` versus \`tag_index.json\`, and automatic lookup recovery. Add a concise changelog entry.

- [ ] **Step 4: Review the final diff and status**

\`\`\`powershell
git status --short
git diff --stat
\`\`\`

Confirm unrelated existing changes are preserved and only requested feature files plus the plan/spec/docs are included.
