# Meme Capture Score Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require a conservative `meme_score` quality gate so ordinary photos, screenshots, informational images, and non-reusable scene images are rejected before they enter the capture catalog.

**Architecture:** Keep the existing capture pipeline and hard rejection rules, add one shared score normalizer and a fixed `meme_score >= 70` gate in `collector.py`, and make both single-image and batch vision prompts emit the same rubric and field. Persist the normalized score only on accepted capture catalog entries; do not change the v4 library-index contract or delete existing user images.

**Tech Stack:** Python 3, `unittest`, JSON vision-model contracts, existing `CapturePipeline`, existing catalog storage.

## Global Constraints

- `MEME_SCORE_THRESHOLD = 70`; score `70` is accepted when all other gates pass.
- Missing, invalid, non-finite, boolean, or out-of-range scores are rejected fail-closed.
- Existing `is_meme`, confidence, allowed `content_type`, screenshot/photo/document/UI flags, and `has_expression` rules remain active.
- Single-image and batch capture prompts must describe the same positive and negative meme criteria and require the same `meme_score` field.
- Low-score images return the existing `not_meme` capture status and never create a file or capture activity record.
- Existing rejected or pending images are not automatically deleted or reclassified by this change.
- `LIBRARY_INDEX_VERSION` and the v4 full-reindex completeness contract do not change.
- Every production change is preceded by a failing test and followed by the focused test plus the full regression suite.

---

### Task 1: Add and enforce the pure meme-score gate

**Files:**
- Modify: `tests/test_collector_requests.py`
- Modify: `tests/test_capture_pipeline.py`
- Modify: `collector.py`

**Interfaces:**
- Produces `collector.MEME_SCORE_THRESHOLD == 70.0`.
- Produces `collector.normalize_meme_score(value: Any) -> float | None` for shared validation and catalog persistence.
- Keeps `collector.should_skip_meme_result(vision: Any, rejection_confidence: float = 0.7) -> bool` backward-compatible while adding the score gate.

- [ ] **Step 1: Write the failing score-gate tests**

In `tests/test_collector_requests.py`, define the fixture before the test methods and add the tests below:

```python
def valid_meme_result(**overrides):
    result = {
        "is_meme": True,
        "confidence": 0.95,
        "meme_score": 85,
        "content_type": "reaction_meme",
        "has_expression": True,
        "is_screenshot": False,
        "is_chat_screenshot": False,
        "is_document": False,
        "is_ui": False,
        "is_photo": False,
        "is_webpage": False,
        "is_poster": False,
        "is_banner": False,
        "is_receipt": False,
    }
    result.update(overrides)
    return result

def test_capture_classifier_accepts_score_at_threshold(self):
    accepted = valid_meme_result(meme_score=70)
    self.assertFalse(should_skip_meme_result(accepted))

def test_capture_classifier_rejects_score_below_threshold(self):
    self.assertTrue(should_skip_meme_result(valid_meme_result(meme_score=69)))

def test_capture_classifier_rejects_missing_or_invalid_score(self):
    for value in (None, True, False, "not-a-number", float("nan"), float("inf"), -1, 101):
        with self.subTest(value=value):
            result = valid_meme_result()
            if value is None:
                result.pop("meme_score")
            else:
                result["meme_score"] = value
            self.assertTrue(should_skip_meme_result(result))

def test_capture_classifier_score_does_not_override_hard_rejections(self):
    result = valid_meme_result(meme_score=100)
    result["is_photo"] = True
    self.assertTrue(should_skip_meme_result(result))
```

The fixture must retain `is_meme=True`, `confidence=0.95`, an allowed `content_type`, and all false hard-rejection flags so each test isolates the score behavior.

In `tests/test_capture_pipeline.py`, extend the existing `_pipeline` helper with optional `vision=None` and `should_skip=None` arguments. The injected recognizer must return `vision` when provided, and the pipeline constructor must use `should_skip or (lambda _vision: False)`. Add this boundary test using the real gate:

```python
def test_low_score_capture_is_not_saved_or_recorded(self):
    async def run():
        with tempfile.TemporaryDirectory() as temporary:
            store = MemeStore(Path(temporary) / "pack")
            payload = SimpleNamespace(content=b"low-score-image", extension=".png")
            events = []
            vision = {
                "is_meme": True,
                "confidence": 0.99,
                "meme_score": 69,
                "content_type": "reaction_meme",
                "has_expression": True,
            }
            pipeline = self._pipeline(
                store=store,
                payload=payload,
                blacklist=None,
                events=events,
                calls={"loader": 0, "recognize": 0, "classify": 0},
                vision=vision,
                should_skip=should_skip_meme_result,
            )
            statuses = await pipeline.process_batch(None, ["source"], "message", "outline")
            return statuses, events, store.image_paths()

    statuses, events, images = asyncio.run(run())
    self.assertEqual(statuses, ["not_meme"])
    self.assertEqual(events, [])
    self.assertEqual(images, [])
```

The pipeline test must import `should_skip_meme_result` from `collector.py`; it verifies that a low score exits before classification and saving, not merely that the pure helper returns `True`.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run:

```powershell
python -m unittest tests.test_collector_requests tests.test_capture_pipeline -v
```

Expected result: the new threshold/missing/invalid-score assertions and the low-score pipeline test fail because the current parser does not require `meme_score`.

- [ ] **Step 3: Implement the smallest shared normalizer and gate**

In `collector.py`:

```python
MEME_SCORE_THRESHOLD = 70.0

def normalize_meme_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score) or not 0.0 <= score <= 100.0:
        return None
    return score
```

Inside `should_skip_meme_result`, validate `meme_score` immediately after the existing confidence check and return `True` when the normalized value is missing or below `MEME_SCORE_THRESHOLD`. Leave the current content-type and flag checks unchanged.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```powershell
python -m unittest tests.test_collector_requests tests.test_capture_pipeline -v
```

Expected result: all collector and low-score pipeline tests pass, including the exact threshold boundary and fail-closed invalid values.

- [ ] **Step 5: Commit the isolated gate change**

```powershell
git add tests/test_collector_requests.py tests/test_capture_pipeline.py collector.py
git commit -m "feat: require meme score for capture"
```

### Task 2: Align single-image and batch vision prompts with the scoring rubric

**Files:**
- Modify: `tests/test_primary_semantic_index.py`
- Modify: `capture.py`
- Modify: `capture_pipeline.py`

**Interfaces:**
- `VISION_SYSTEM_PROMPT` and `VISION_BATCH_SYSTEM_PROMPT` both require numeric `meme_score` in the `0–100` range.
- Both prompts include the same positive evidence and negative evidence from the approved design.
- Both prompts state that uncertain cases must be rejected and message context cannot upgrade an informational image into a meme.

- [ ] **Step 1: Write the failing prompt-contract assertions**

Extend `test_capture_prompts_require_strict_content_type_and_rejection_flags` with assertions for both capture prompts:

```python
for prompt in (VISION_SYSTEM_PROMPT, VISION_BATCH_SYSTEM_PROMPT):
    self.assertIn("meme_score", prompt)
    self.assertIn("0–100", prompt)
    self.assertIn("普通照片", prompt)
    self.assertIn("聊天记录截图", prompt)
    self.assertIn("脱离原始场景", prompt)
    self.assertIn("无法确认时宁可拒绝", prompt)
```

- [ ] **Step 2: Run the prompt tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_primary_semantic_index -v
```

Expected result: the new assertions fail because the current prompts do not mention `meme_score` or the complete rubric.

- [ ] **Step 3: Update both prompts with the same contract**

Add to the single-image prompt and copy the same decision rules into the batch prompt. The JSON example must include:

```json
"meme_score": 0,
"rejection_reason": "不合格时填写原因，否则为空"
```

The prompt must classify a picture as a meme only when it is reusable for expressing emotion, attitude, reaction, teasing, or a joke. It must explicitly reject ordinary photos/selfies/scenery, game/software/web/chat screenshots, QR codes, product images, tutorial/data/error images, and plain anime/movie frames without meme use. It must say that the user message is supporting context only.

- [ ] **Step 4: Run the prompt tests and verify they pass**

Run:

```powershell
python -m unittest tests.test_primary_semantic_index -v
```

Expected result: all primary semantic and prompt contract tests pass.

- [ ] **Step 5: Commit the prompt contract change**

```powershell
git add tests/test_primary_semantic_index.py capture.py capture_pipeline.py
git commit -m "feat: add meme score rubric to capture prompts"
```

### Task 3: Persist the normalized score on accepted capture entries

**Files:**
- Modify: `tests/test_primary_semantic_index.py`
- Modify: `capture.py`

**Interfaces:**
- `CaptureMixin._catalog_entry_from_vision(...)` adds `meme_score` only when `normalize_meme_score` returns a valid value.
- Stored values are normalized finite floats in the inclusive `0–100` range.
- The field is optional for compatibility when `only_capture_memes` is disabled or an older caller supplies no score; v4 completeness does not require it.

- [ ] **Step 1: Write the failing persistence test**

In `tests/test_primary_semantic_index.py`, import `tempfile`, `Path`, and `CaptureMixin` from `meme_manager_master.capture`, then add a temporary-image test around the existing static catalog-entry builder:

```python
def test_capture_catalog_entry_keeps_normalized_meme_score(self):
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "reaction.png"
        path.write_bytes(b"image")
        entry = CaptureMixin._catalog_entry_from_vision(
            path,
            "尴尬",
            {"meme_score": "86.5", "description": "反应"},
            {},
        )
    self.assertEqual(entry["meme_score"], 86.5)
```

- [ ] **Step 2: Run the persistence test and verify it fails**

Run:

```powershell
python -m unittest tests.test_primary_semantic_index -v
```

Expected result: the new assertion fails because `_catalog_entry_from_vision` currently does not copy the score.

- [ ] **Step 3: Add score persistence without changing v4 requirements**

Import `normalize_meme_score` in `capture.py`, normalize `vision.get("meme_score")`, and add the `meme_score` key to the returned entry only when the value is not `None`. Do not add it to `full_reindex_entry_is_current` or change `LIBRARY_INDEX_VERSION`.

- [ ] **Step 4: Run the persistence and capture regression tests**

Run:

```powershell
python -m unittest tests.test_primary_semantic_index tests.test_capture_pipeline -v
```

Expected result: the new score field is retained and existing save/duplicate pipeline tests remain green.

- [ ] **Step 5: Commit the catalog persistence change**

```powershell
git add tests/test_primary_semantic_index.py capture.py
git commit -m "feat: retain capture meme score"
```

### Task 4: Update release notes and run repository-wide verification

**Files:**
- Modify: `CHANGELOG.md`
- Test: `tests/test_collector_requests.py`
- Test: `tests/test_primary_semantic_index.py`
- Test: `tests/test_capture_pipeline.py`

**Interfaces:**
- Release notes describe the stricter `meme_score >= 70` gate, the rejected image classes, and the fact that historical false positives are not deleted automatically.

- [ ] **Step 1: Add the changelog entry**

Add a concise entry under the current unreleased section:

```text
- 收紧表情包偷取识别：视觉模型必须输出 0–100 的 meme_score，低于 70 或属于普通照片、截图、信息图等非表情包图片时直接拒绝保存。
```

- [ ] **Step 2: Run focused checks**

```powershell
python -m unittest tests.test_collector_requests tests.test_primary_semantic_index tests.test_capture_pipeline -v
python -m compileall -q .
git diff --check
```

Expected result: all focused tests pass, compilation succeeds, and `git diff --check` reports no whitespace errors.

- [ ] **Step 3: Run the repository verification suite**

```powershell
$jsFiles = rg --files pages -g '*.js'; foreach ($file in $jsFiles) { node --check $file; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
python -m unittest discover -s tests -v
```

Expected result: schema is in sync, architecture checks pass, all JavaScript files parse, and the complete unittest suite passes.

- [ ] **Step 4: Inspect the final diff and status**

```powershell
git diff --stat HEAD~5..HEAD
git status --short
```

Confirm only the intended capture, prompt, test, changelog, design, and plan files are part of the implementation commits; do not stage `.superpowers/brainstorm/` mockup artifacts.

- [ ] **Step 5: Commit the release-note and verification change**

```powershell
git add CHANGELOG.md
git commit -m "docs: document stricter meme capture filtering"
```
