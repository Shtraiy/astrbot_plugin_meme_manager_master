# WebUI Sandbox Navigation Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore clickable navigation from the `a_manage` plugin Page to its nested index, settings, and catalog documents without attempting forbidden top-level iframe navigation.

**Architecture:** Keep all user-facing navigation inside the registered `a_manage` Page root. Navigation initialization updates the already rewritten relative link URL with `view` and `managed_pack_id`, removes any `target`, and never constructs a Dashboard route or reads `asset_token` by name.

**Tech Stack:** Native JavaScript, static HTML, Python `unittest`, Node.js VM runtime tests, Git.

## Global Constraints

- Do not set or emit `target="_top"` in `pages/a_manage/` navigation.
- Do not construct `/#/plugin-page/meme_manager_master/<page>` from inside the sandboxed iframe.
- Do not read, parse, or name `asset_token` in production JavaScript.
- Preserve only the `view` and `managed_pack_id` business parameters when updating links.
- Keep backend APIs and page business logic unchanged.

---

### Task 1: Add a failing runtime regression test

**Files:**
- Modify: `tests/test_webui_navigation_auth.py`

**Interfaces:**
- Consumes: `window.MemeManagerUI.api.applySecureNavLinks()` from `pages/a_manage/api.js`.
- Produces: a Node VM regression test proving that the real helper keeps navigation in the current iframe and carries business parameters.

- [x] **Step 1: Add the runtime test harness**

Add `json`, `subprocess`, and `textwrap` imports. Add a test that evaluates `pages/a_manage/api.js` with three real link doubles whose `href` values point to nested `a_manage` content URLs. The harness must call `applySecureNavLinks()` and print each resulting `href` and `target`.

The expected values are literals:

```python
self.assertEqual(
    result["semantic"],
    {
        "path": "/api/plugin/page/content/meme_manager_master/a_manage/semantic/index.html",
        "managed_pack_id": "pack-a",
        "view": None,
        "target": None,
    },
)
self.assertEqual(result["catalog"]["view"], "catalog")
self.assertNotIn("plugin-page/meme_manager_master", result["settings"]["href"])
```

The link doubles must implement `getAttribute`, `removeAttribute`, and mutable `href`/`target` properties so the real production helper is exercised.

- [x] **Step 2: Replace the obsolete static contract**

Update the existing navigation assertions to require relative links in `pages/a_manage/index.html`, require no `target="_top"` in all four `pages/a_manage` HTML files, and require no Dashboard route builder or `_top` assignment in the four `pages/a_manage` navigation scripts.

- [x] **Step 3: Verify RED**

Run:

```powershell
python -m unittest tests.test_webui_navigation_auth -v
```

Expected: FAIL because the current implementation rewrites links to Dashboard hash routes and sets `_top`.

### Task 2: Restore in-frame navigation

**Files:**
- Modify: `pages/a_manage/api.js`
- Modify: `pages/a_manage/index.html`
- Modify: `pages/a_manage/catalog/index.html`
- Modify: `pages/a_manage/catalog/script.js`
- Modify: `pages/a_manage/settings/index.html`
- Modify: `pages/a_manage/settings/script.js`
- Modify: `pages/a_manage/semantic/index.html`
- Modify: `pages/a_manage/semantic/script.js`

**Interfaces:**
- Consumes: server-rewritten `link.href`, `window.location.search`, and `data-nav-page`/`data-nav-view`.
- Produces: links that navigate the current iframe and preserve `view`/`managed_pack_id`.

- [x] **Step 1: Implement the main-page helper**

Replace the Dashboard route builder in `pages/a_manage/api.js` with logic equivalent to:

```js
window.MemeManagerUI.api.applySecureNavLinks = function () {
  const allowedPages = new Set(["a_manage", "catalog", "settings", "semantic"]);
  const currentParams = new URLSearchParams(window.location.search);
  document.querySelectorAll("a[data-nav-page]").forEach((link) => {
    const pageName = link.getAttribute("data-nav-page");
    if (!allowedPages.has(pageName)) return;
    const nextUrl = new URL(link.href, window.location.href);
    const navView = link.getAttribute("data-nav-view") || "";
    if (navView) nextUrl.searchParams.set("view", navView);
    else nextUrl.searchParams.delete("view");
    const managedPackId = currentParams.get("managed_pack_id");
    if (managedPackId) nextUrl.searchParams.set("managed_pack_id", managedPackId);
    else nextUrl.searchParams.delete("managed_pack_id");
    link.removeAttribute("target");
    link.href = nextUrl.toString();
  });
};
```

- [x] **Step 2: Restore relative fallback links**

Use these main-page paths:

```text
./semantic/index.html
./catalog/index.html
./settings/index.html
```

Use `../index.html` and sibling `../<page>/index.html` paths in the three nested `a_manage` HTML pages. Remove every `target="_top"`.

- [x] **Step 3: Update nested page initializers**

In the catalog, settings, and semantic scripts, replace Dashboard hash construction with the same existing-link update behavior used by the main helper. Keep each page's existing initialization order and business code unchanged.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
python -m unittest tests.test_webui_navigation_auth -v
node --check pages/a_manage/api.js
node --check pages/a_manage/catalog/script.js
node --check pages/a_manage/settings/script.js
node --check pages/a_manage/semantic/script.js
```

Expected: all commands pass.

### Task 3: Release metadata and verification

**Files:**
- Modify: `metadata.yaml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: AstrBot plugin release `v2.1.4` with a changelog entry describing the sandbox navigation regression fix.

- [x] **Step 1: Update release metadata**

Set `metadata.yaml` and the README badge to `v2.1.4`. Add `## [v2.1.4] - 2026-08-11` at the top of `CHANGELOG.md` with a `修复` entry for index/settings links being blocked by the iframe sandbox.

- [x] **Step 2: Run focused and full verification**

Run:

```powershell
python -m unittest tests.test_webui_navigation_auth tests.test_capture_index_page tests.test_capture_index_runtime -v
python -m unittest discover -s tests -p 'test_*.py' -v
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
git diff --check
```

Expected: navigation and capture-index tests pass. If the existing PNG byte-equality baseline failure remains in `tests.test_models_upload_security`, report it separately and verify no new failure was introduced.

- [x] **Step 3: Commit and push**

```powershell
git add tests/test_webui_navigation_auth.py pages/a_manage metadata.yaml README.md CHANGELOG.md docs/superpowers/plans/2026-08-11-webui-sandbox-navigation-hotfix.md
git commit -m "fix: restore sandbox-safe page navigation"
git push origin main
```
