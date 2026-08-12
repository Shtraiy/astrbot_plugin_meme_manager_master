# Contextual Capture Batch Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant unified-disposal toolbar button and make a selected card's disposal button process every selected item from the same workspace section.

**Architecture:** Keep `selectedItems` as the single selection source and add a small client-side selector that maps a clicked disposal item to either the indexed group or the pending/duplicate group. Reuse the existing confirmation, `capture/items/dispose` request, refresh, and partial-failure paths; the backend and persisted data formats remain unchanged.

**Tech Stack:** Native HTML/CSS/JavaScript, Node.js runtime harness executed from Python `unittest`, Python 3 `unittest`, Git.

## Global Constraints

- A selected pending-card action processes selected `pending` and `duplicate` items only; selected `indexed` items remain selected.
- A selected indexed-card action processes selected `indexed` items only; selected pending items remain selected.
- A non-selected card, or any card outside batch mode, still processes exactly one item.
- Remove `capture-dispose-selected-button` from both page copies while retaining current-page/current-view selection and clear-selection controls.
- Successful items lose selection, failed items remain selected, and no backend route or payload schema changes.
- Keep both page copies synchronized without changing their navigation behavior.
- Update `CHANGELOG.md`; do not change public configuration, `_conf_schema.json`, `metadata.yaml`, or the plugin version.

---

### Task 1: Lock the contextual interaction contract with failing tests

**Files:**
- Modify: `tests/test_capture_index_page.py`
- Modify: `tests/test_capture_index_runtime.py`

**Interfaces:**
- Consumes: existing DOM IDs, `selectedItems`, card action buttons, and the `capture/items/dispose` fake API.
- Produces: regression expectations for `disposalItemsForAction(item)` and for the absence of `capture-dispose-selected-button`/`disposeSelectedItems`.

- [ ] **Step 1: Replace the obsolete static toolbar assertions**

Update the page-contract test so both page copies must retain the three selection controls but omit the global action:

```python
self.assertIn("capture-selection-mode-button", source)
self.assertIn("capture-select-indexed-page-button", source)
self.assertIn("capture-select-pending-button", source)
self.assertIn("capture-clear-selection-button", source)
self.assertNotIn("capture-dispose-selected-button", source)
self.assertIn("selectedItems", script)
self.assertIn("toggleVisibleSelection", script)
self.assertIn("disposalItemsForAction", script)
self.assertNotIn("disposeSelectedItems", script)
```

Also remove the obsolete positive assertion from `test_capture_index_page_is_available` and change the expected script cache version to `20260812-contextual-batch-1` while leaving the existing stylesheet version unchanged.

- [ ] **Step 2: Change the runtime harness to click selected card actions**

Remove `capture-dispose-selected-button` from the fake DOM ID list. In the batch scenario, explicitly enable selection mode, select the visible pending view, select at least one indexed card, then click the action button of a selected pending card. Capture the final disposal request as `pendingBatchPayload` and record that the indexed selection remains in the summary.

Then clear/rebuild selection, select at least two indexed cards plus one pending card, click an action button on a selected indexed card, capture `indexedBatchPayload`, and record that the pending selection remains in the summary. Assertions must compare exact kinds:

```python
self.assertEqual(
    {item["kind"] for item in payload["pendingBatchPayload"]["items"]},
    {"pending", "duplicate"},
)
self.assertNotIn(
    "indexed",
    {item["kind"] for item in payload["pendingBatchPayload"]["items"]},
)
self.assertEqual(
    {item["kind"] for item in payload["indexedBatchPayload"]["items"]},
    {"indexed"},
)
self.assertTrue(payload["indexedSelectionPreservedAfterPendingBatch"])
self.assertTrue(payload["pendingSelectionPreservedAfterIndexedBatch"])
```

Keep the existing single-item checks so they continue proving that clicking an unselected card action submits exactly one item.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_capture_index_page tests.test_capture_index_runtime -v
```

Expected: FAIL because both HTML files still contain `capture-dispose-selected-button`, both scripts still contain `disposeSelectedItems`, and selected card actions still submit `[disposal]` only.

### Task 2: Implement same-section card-triggered batch disposal

**Files:**
- Modify: `pages/semantic/index.html`
- Modify: `pages/a_manage/semantic/index.html`
- Modify: `pages/semantic/script.js`
- Modify: `pages/a_manage/semantic/script.js`

**Interfaces:**
- Consumes: `selectionMode: boolean`, `selectedItems: Map<string, DisposalItem>`, `selectionKey(item)`, and `disposeCaptureItems(items, button)`.
- Produces: `disposalItemsForAction(item): DisposalItem[]`, where `DisposalItem` is `{kind: "indexed"|"pending", filename: string}` or `{kind: "duplicate", sha256: string}`.

- [ ] **Step 1: Remove the redundant toolbar control**

Delete this element from both HTML files:

```html
<button id="capture-dispose-selected-button" type="button" class="primary" hidden disabled>统一处理</button>
```

Update only the `script.js` query string in both files to `20260812-contextual-batch-1` so browsers do not reuse the old click behavior.

- [ ] **Step 2: Add the minimal same-section selector to both scripts**

Place the helper next to the other selection helpers:

```javascript
function disposalItemsForAction(item) {
  const key = selectionKey(item);
  if (!selectionMode || !key || !selectedItems.has(key)) return [item];
  const indexedAction = item.kind === "indexed";
  const matching = [...selectedItems.values()].filter((selected) =>
    indexedAction ? selected.kind === "indexed" : selected.kind !== "indexed"
  );
  return matching.length ? matching : [item];
}
```

This helper relies on selection state rather than card CSS and includes `pending` plus `duplicate` in the pending group.

- [ ] **Step 3: Route card actions through the helper and remove dead global-button code**

Change both card handlers to:

```javascript
deleteButton.addEventListener("click", (event) => {
  event.stopPropagation();
  void disposeCaptureItems(disposalItemsForAction(disposal), deleteButton);
});
```

Remove the `disposeSelectedButton` DOM query, its `updateSelectionUi` state block, the `disposeSelectedItems` function, and its bottom-level click listener. Do not alter `disposeCaptureItems` or backend calls.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_capture_index_page tests.test_capture_index_runtime -v
```

Expected: all focused tests pass for both page copies, including exact request grouping and opposite-section selection preservation.

- [ ] **Step 5: Check both modified scripts directly**

Run:

```powershell
node --check pages/semantic/script.js
node --check pages/a_manage/semantic/script.js
```

Expected: both commands exit 0 without syntax errors.

### Task 3: Document and verify the finished behavior

**Files:**
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: the completed user-visible interaction and fresh verification output.
- Produces: an `[Unreleased]` changelog entry describing contextual same-section batch disposal and removal of the global control.

- [ ] **Step 1: Update the changelog**

Add a `[Unreleased]` change entry:

```markdown
- 批量选择时，点击任意已选卡片的处置按钮会批量处理同一区域的选择：已整理与待处理互不混入；移除冗余的“统一处理”工具栏按钮，未选卡片仍保持单项处置。
```

Do not change the version, metadata, README, configuration, or schema files.

- [ ] **Step 2: Run all project verification gates**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
git diff --check
```

Expected: every command exits 0; record the fresh unittest count and any existing skip in `CHANGELOG.md` only if the verification entry itself needs refreshing.

- [ ] **Step 3: Review the final diff against the spec**

Confirm with `git diff --stat`, `git diff`, and `git status --short` that only the two HTML files, two scripts, two target test files, and `CHANGELOG.md` changed. Confirm no debug output, generated artifacts, credentials, or unrelated formatting are present.

- [ ] **Step 4: Stage and commit the implementation**

Stage only the task files, run `git diff --cached --check`, and create:

```text
fix: trigger capture batch disposal from selected cards

Summary:
- group card-triggered disposal by indexed or pending selection
- remove the redundant unified processing toolbar button

Tests:
- python -m unittest discover -s tests -v
- python -m compileall -q .
- python scripts/generate_conf_schema.py --check
- python scripts/check_architecture.py
- all page JavaScript node --check
- git diff --cached --check

Metadata:
- CHANGELOG updated
- no version or schema changes
```

- [ ] **Step 5: Report remote-upload status accurately**

Do not push without fresh explicit authorization for this new implementation commit. Report the local commit ID and that live AstrBot WebUI interaction remains unverified if the host is unavailable.
