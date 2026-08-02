# Indexed Emoji Thumbnail Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将表情索引页的已整理/待分类文字卡片升级为带 `preview` 缩略图、状态文本、错误重试和响应式布局的卡片，同时不修改后端 API 或普通管理页。

**Architecture:** `pages/semantic/script.js` 在现有 `renderCard()` 内创建固定比例缩略图容器，通过已有 `meme_image_data` 接口请求 `size: "preview"` 的 Data URL；卡片点击仍调用原图 `showPreview(item)`，缩略图请求失败时卡片进入错误态，下一次点击重试缩略图。`pages/semantic/style.css` 负责占位、成功、失败、重复状态、键盘聚焦和响应式网格。

**Tech Stack:** 原生 JavaScript、静态 CSS、Python `unittest`、Node `--check`。

## Global Constraints

- 只修改 `pages/semantic` 页面及其静态回归测试；不修改 `pages/a_manage/semantic`。
- 图片地址只能来自已有 `meme_image_data` API 返回的 `data_url`，不得拼接本地绝对路径。
- 不新增后端接口，不改变 API 数据结构，不修改普通表情管理页。
- 用户可见文本使用 `textContent` 或元素属性写入，不引入动态 HTML。
- 缩略图请求使用 `size: "preview"`；点击查看原图继续使用 `size: "original"`。

---

### Task 1: Add failing static regression tests

**Files:**
- Create: `tests/test_indexed_emoji_thumbnail_cards.py`

**Interfaces:**
- Tests inspect the source-level contract of `pages/semantic/script.js` and `pages/semantic/style.css`.
- The implementation must expose the existing `renderCard`/`showPreview` behavior in source form without changing their external page API.

- [x] **Step 1: Write the failing source-contract tests**

Create the test file with:

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IndexedEmojiThumbnailCardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "pages" / "semantic" / "script.js").read_text(
            encoding="utf-8"
        )
        cls.style = (ROOT / "pages" / "semantic" / "style.css").read_text(
            encoding="utf-8"
        )

    def test_cards_render_thumbnail_with_accessible_filename_and_status(self):
        self.assertIn('className = "card-thumbnail"', self.script)
        self.assertIn('image.loading = "lazy"', self.script)
        self.assertIn('card.title = item.filename || "未命名图片"', self.script)
        self.assertIn("thumbnail-placeholder", self.script)
        self.assertIn("thumbnail-error", self.script)

    def test_thumbnail_uses_preview_api_and_original_preview_stays_original(self):
        self.assertIn('apiGet("meme_image_data"', self.script)
        self.assertIn('size: "preview"', self.script)
        self.assertIn('size: "original"', self.script)
        self.assertIn("data.data_url", self.script)

    def test_failed_thumbnail_can_be_retried_without_removing_card_preview(self):
        self.assertIn("loadThumbnail(item, image, card)", self.script)
        self.assertIn('card.classList.contains("thumbnail-error")', self.script)
        self.assertIn("点击重试", self.script)
        self.assertIn('card.addEventListener("click"', self.script)

    def test_thumbnail_styles_cover_grid_ratio_focus_and_reduced_motion(self):
        self.assertIn("grid-template-columns: repeat(auto-fill", self.style)
        self.assertIn(".card-thumbnail", self.style)
        self.assertIn("aspect-ratio:", self.style)
        self.assertIn(":focus-visible", self.style)
        self.assertIn("prefers-reduced-motion", self.style)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the focused test and verify it fails for the current text-only cards**

Run:

```powershell
python -m unittest tests.test_indexed_emoji_thumbnail_cards -v
```

Expected: FAIL because the current script has no thumbnail element, preview-size request, retry state, or thumbnail CSS.

- [ ] **Step 3: Commit the regression test**

```powershell
git add tests/test_indexed_emoji_thumbnail_cards.py
git commit -m "test: define indexed emoji thumbnail card contract"
```

### Task 2: Implement thumbnail loading and card semantics

**Files:**
- Modify: `pages/semantic/script.js:62-97`

**Interfaces:**
- `getImageLocation(item)` returns `{ managed_pack_id, category, filename }` or `null`.
- `showPreview(item)` continues to call `meme_image_data` with `size: "original"`.
- `loadThumbnail(item, image, card)` calls `meme_image_data` with `size: "preview"`, writes only the returned `data_url`, and toggles loading/error/success classes.
- `renderCard(item, target)` creates the same clickable card for indexed and pending entries.

- [x] **Step 1: Extract the shared safe image-location parser**

Immediately before `showPreview`, add:

```js
  function getImageLocation(item) {
    const relative = String(item.relative_path || "").split("/");
    const filename = relative.pop() || "";
    const category = relative[relative.length - 1] || "";
    if (!category || !filename || !packSelect.value) return null;
    return {
      managed_pack_id: packSelect.value,
      category,
      filename,
    };
  }
```

- [x] **Step 2: Keep the existing original-preview request on the shared parser**

Replace the path parsing and guard at the beginning of `showPreview` with:

```js
    const location = getImageLocation(item);
    if (!location) return;
```

Keep the existing API call and add `...location` before `size: "original"` so the endpoint and original-size behavior remain unchanged.

- [x] **Step 3: Add the preview-size thumbnail loader with explicit states**

Immediately after `showPreview`, add:

```js
  async function loadThumbnail(item, image, card) {
    const location = getImageLocation(item);
    if (!location) return;
    card.classList.remove("thumbnail-error", "thumbnail-loaded");
    card.classList.add("thumbnail-loading");
    try {
      const data = await apiGet("meme_image_data", {
        ...location,
        size: "preview",
      });
      if (!data.data_url) throw new Error("缩略图数据为空");
      image.src = data.data_url;
      card.classList.remove("thumbnail-loading");
      card.classList.add("thumbnail-loaded");
    } catch (error) {
      image.removeAttribute("src");
      card.classList.remove("thumbnail-loading");
      card.classList.add("thumbnail-error");
    }
  }
```

Do not call `showError` for every thumbnail failure; the card itself carries the local error state and retry affordance while the page-level notice remains available for workspace/API failures.

- [x] **Step 4: Replace the text-only card body with an accessible thumbnail card**

Replace `renderCard` with:

```js
  function renderCard(item, target) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `card thumbnail-loading${item.duplicate ? " duplicate" : ""}`;
    card.title = item.filename || "未命名图片";
    card.addEventListener("click", () => {
      if (card.classList.contains("thumbnail-error")) {
        void loadThumbnail(item, image, card);
        return;
      }
      void showPreview(item);
    });

    const thumbnail = document.createElement("span");
    thumbnail.className = "card-thumbnail";
    thumbnail.setAttribute("aria-hidden", "true");
    const image = document.createElement("img");
    image.className = "thumbnail-image";
    image.loading = "lazy";
    image.alt = "";
    const placeholder = document.createElement("span");
    placeholder.className = "thumbnail-placeholder";
    placeholder.textContent = "加载缩略图";
    const errorText = document.createElement("span");
    errorText.className = "thumbnail-error-text";
    errorText.textContent = "缩略图加载失败，点击重试";
    thumbnail.append(image, placeholder, errorText);

    const title = document.createElement("strong");
    title.textContent = item.filename || "未命名图片";
    const meta = document.createElement("span");
    meta.textContent = `${item.category || "未分类"} · ${
      item.duplicate ? "重复待去重" : item.indexed ? "已索引" : "待分类"
    }`;
    const description = document.createElement("small");
    description.textContent = item.description || "点击查看图片";
    card.setAttribute("aria-label", `${title.textContent}，${meta.textContent}`);
    card.append(thumbnail, title, meta, description);
    target.append(card);
    void loadThumbnail(item, image, card);
  }
```

The `image` declaration must remain before the click handler is invoked at runtime; JavaScript closure capture is sufficient because the handler runs after construction. Keep all text assignments through `textContent`.

- [x] **Step 5: Run the focused test and syntax check**

Run:

```powershell
python -m unittest tests.test_indexed_emoji_thumbnail_cards -v
node --check pages/semantic/script.js
```

Expected: all four Python tests PASS and Node reports no syntax errors.

- [ ] **Step 6: Commit the script implementation**

```powershell
git add pages/semantic/script.js tests/test_indexed_emoji_thumbnail_cards.py
git commit -m "feat: render indexed emoji thumbnail cards"
```

### Task 3: Add responsive thumbnail and interaction styles

**Files:**
- Modify: `pages/semantic/style.css:39-50`

**Interfaces:**
- `.cards` remains the shared grid for both indexed and pending lists.
- `.card-thumbnail` is a fixed-ratio visual region.
- `.thumbnail-loading`, `.thumbnail-loaded`, and `.thumbnail-error` communicate the async state without changing card data.

- [x] **Step 1: Replace the card/grid rules with the thumbnail-card layout**

Use these rules in place of the current `.cards`/`.card` block while retaining the existing duplicate and empty rules:

```css
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.card {
  display: grid;
  gap: 7px;
  min-height: 220px;
  padding: 10px;
  overflow: hidden;
  text-align: left;
  background: #f9fdfc;
  transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}
.card:hover,
.card:focus-visible {
  border-color: #218a73;
  box-shadow: 0 10px 22px rgba(33, 126, 103, .16);
  outline: none;
  transform: translateY(-1px);
}
.card-thumbnail {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: 10px;
  background: #eaf4f2;
  color: #76918f;
  font-size: 12px;
}
.thumbnail-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
}
.thumbnail-placeholder,
.thumbnail-error-text {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 12px;
  text-align: center;
}
.thumbnail-error-text { display: none; color: #a34d3d; }
.card.thumbnail-loaded .thumbnail-image { opacity: 1; }
.card.thumbnail-loaded .thumbnail-placeholder,
.card.thumbnail-error .thumbnail-placeholder { display: none; }
.card.thumbnail-error .thumbnail-error-text { display: grid; }
.card strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card span { color: #20846d; font-size: 12px; }
.card small { color: #6d7d87; }
.card.duplicate { border-color: #e4b978; background: #fffaf0; }
```

- [x] **Step 2: Make the narrow layout use two card columns**

Extend the existing media query with:

```css
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .card { min-height: 190px; padding: 8px; }
```

This keeps the summary/columns stacking behavior while preserving two thumbnail columns on narrow screens.

- [x] **Step 3: Respect reduced-motion preferences**

Append:

```css
@media (prefers-reduced-motion: reduce) {
  .card { transition: none; }
}
```

- [x] **Step 4: Run style contract, syntax, and whitespace checks**

Run:

```powershell
python -m unittest tests.test_indexed_emoji_thumbnail_cards -v
node --check pages/semantic/script.js
git diff --check
```

Expected: all focused tests pass, JavaScript parses, and `git diff --check` produces no output.

- [ ] **Step 5: Commit the style implementation**

```powershell
git add pages/semantic/style.css
git commit -m "style: add responsive indexed emoji thumbnails"
```

### Task 4: Full verification and visual handoff

**Files:**
- Verify: `pages/semantic/index.html`
- Verify: `pages/semantic/script.js`
- Verify: `pages/semantic/style.css`
- Test: `tests/`

**Interfaces:**
- No new runtime API. The final page must preserve `capture/workspace`, `capture/index`, original preview, and pending-item rendering.

- [x] **Step 1: Run the complete Python suite**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass with zero failures and zero errors.

- [x] **Step 2: Run the required JavaScript syntax checks**

Run:

```powershell
node --check pages/semantic/script.js
node --check pages/a_manage/semantic/script.js
```

Expected: both commands complete successfully; only `pages/semantic` was changed.

- [x] **Step 3: Check the final patch**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; the changed-file list contains only the semantic page files, the focused test, and the implementation plan.

- [ ] **Step 4: Perform browser acceptance checks**

Open the index page in desktop and narrow browser widths and verify:

1. Indexed and pending cards both show thumbnails, filename, category/status, and description.
2. Initial thumbnail state is visible before the preview response resolves.
3. A missing/failed preview enters the error state and clicking the card retries it.
4. A successful card click still opens the original-size preview mask.
5. Long filenames remain one-line ellipsized while `title` exposes the full name.
6. Keyboard focus is visible and reduced-motion mode removes the card transition.
