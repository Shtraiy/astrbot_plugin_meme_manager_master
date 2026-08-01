# WebUI Asset Token Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 AstrBot 插件页显示“Token 无效”的问题，让多个管理 Page 通过 Dashboard 顶层路由切换，并完全移除插件侧的 `asset_token` 处理。

**Architecture:** 每个独立 Page 只负责把固定的 Page 名称交给本页导航帮助函数；帮助函数构造 `/#/plugin-page/meme_manager_master/<page>`，仅保留 `view` 和 `managed_pack_id` 业务参数。点击后由 Dashboard 重新创建目标 iframe，让 AstrBot 重新生成静态资源令牌。后端 API 与 `import_token` 不变。

**Tech Stack:** 原生 JavaScript、静态 HTML、Python `unittest`、Node `--check`、Git。

## Global Constraints

- 不手动读取、拼接或转发 `asset_token`。
- 页面间导航不得使用 `../` 跨越当前 Page 根目录。
- 仅允许 `a_manage`、`catalog`、`settings`、`semantic` 四个 Page 名称。
- 不修改后端 Web API、鉴权中间件或导入凭证逻辑。

---

### Task 1: Add failing navigation regression tests

**Files:**
- Modify: `tests/test_webui_navigation_auth.py`

**Interfaces:**
- Tests inspect the source-level navigation contract used by all plugin Pages.
- Later tasks must make the assertions pass without weakening the expected contract.

- [ ] **Step 1: Replace the old token-forwarding expectations with the new contract**

Update `WebUINavigationAuthTests` so it asserts:

```python
    def test_pages_do_not_manually_forward_asset_tokens(self):
        sources = [
            ROOT / "pages" / "a_manage" / "api.js",
            ROOT / "pages" / "catalog" / "script.js",
            ROOT / "pages" / "settings" / "script.js",
            ROOT / "pages" / "semantic" / "script.js",
        ]
        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("asset_token", source, str(path))
            self.assertIn("plugin-page/meme_manager_master", source, str(path))

    def test_page_links_use_named_targets_instead_of_parent_paths(self):
        sources = [
            ROOT / "pages" / "a_manage" / "index.html",
            ROOT / "pages" / "catalog" / "index.html",
            ROOT / "pages" / "settings" / "index.html",
            ROOT / "pages" / "semantic" / "index.html",
        ]
        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("../", source, str(path))
            self.assertIn("data-nav-page", source, str(path))

    def test_entry_redirect_does_not_copy_static_asset_token(self):
        source = (ROOT / "pages" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("asset_token", source)
        self.assertIn("plugin-page/meme_manager_master/a_manage", source)
```

Replace the existing semantic-page assertion with an explicit check that `pages/semantic/index.html` contains `data-nav-page="a_manage"` and no `../`, while `pages/semantic/script.js` contains `plugin-page/meme_manager_master` and no `asset_token`.

- [ ] **Step 2: Run the focused test and verify it fails for the old implementation**

Run:

```powershell
python -m unittest tests.test_webui_navigation_auth -v
```

Expected: FAIL because the old scripts contain `asset_token` and the HTML links contain `../`.

- [ ] **Step 3: Commit the failing test change**

```powershell
git add tests/test_webui_navigation_auth.py
git commit -m "test: define safe plugin page navigation contract"
```

### Task 2: Implement the page-route navigation helper

**Files:**
- Modify: `pages/a_manage/api.js`
- Modify: `pages/catalog/script.js`
- Modify: `pages/settings/script.js`
- Modify: `pages/semantic/script.js`

**Interfaces:**
- Each page exposes a local helper with the existing call shape `withCurrentPageParams(pageName, extraParams = {})` or an equivalent function used by its own link setup.
- `pageName` is one of `a_manage`, `catalog`, `settings`, `semantic`.
- Returned URLs have the form `/#/plugin-page/meme_manager_master/<pageName>` with optional `view` and `managed_pack_id` query values inside the hash.

- [ ] **Step 1: Add the minimal route builder to each page script**

Use this exact behavior in each page-specific helper, adapting only the namespace assignment in `a_manage/api.js`:

```js
const PLUGIN_PAGE_NAMES = new Set(["a_manage", "catalog", "settings", "semantic"]);

function withCurrentPageParams(pageName, extraParams = {}) {
  if (!PLUGIN_PAGE_NAMES.has(pageName)) {
    return null;
  }
  const query = new URLSearchParams(window.location.search);
  for (const [key, value] of Object.entries(extraParams)) {
    if (value === null || value === undefined || value === "") {
      query.delete(key);
    } else {
      query.set(key, String(value));
    }
  }
  const route = new URL(window.location.origin + "/");
  const routeQuery = new URLSearchParams();
  for (const key of ["view", "managed_pack_id"]) {
    const value = query.get(key);
    if (value) {
      routeQuery.set(key, value);
    }
  }
  const suffix = routeQuery.toString() ? `?${routeQuery}` : "";
  route.hash = `/plugin-page/meme_manager_master/${pageName}${suffix}`;
  return route;
}
```

The helper must not mention `asset_token`, use `../`, or construct a static asset content URL. Keep `applySecureNavLinks` behavior limited to reading `data-nav-page`, calling the helper, setting `target="_top"`, and assigning the resulting URL when non-null.

- [ ] **Step 2: Update the pack return link to use the named route**

In `pages/a_manage/pack.js`, change the existing call from:

```js
window.MemeManagerUI.api.withCurrentPageParams("../catalog/index.html", {
```

to:

```js
window.MemeManagerUI.api.withCurrentPageParams("catalog", {
```

- [ ] **Step 3: Run the focused test and verify it passes**

Run:

```powershell
python -m unittest tests.test_webui_navigation_auth -v
```

Expected: PASS.

- [ ] **Step 4: Commit the route-helper implementation**

```powershell
git add pages/a_manage/api.js pages/a_manage/pack.js pages/catalog/script.js pages/settings/script.js pages/semantic/script.js
git commit -m "fix: let dashboard refresh plugin page asset tokens"
```

### Task 3: Update all Page markup and the entry page

**Files:**
- Modify: `pages/a_manage/index.html`
- Modify: `pages/catalog/index.html`
- Modify: `pages/settings/index.html`
- Modify: `pages/semantic/index.html`
- Modify: `pages/index.html`

**Interfaces:**
- Navigation anchors expose `data-nav-page` values matching the fixed Page-name allowlist.
- Their fallback `href` values point at the Dashboard hash route, not a sibling static file.
- The entry page redirects directly to the Dashboard hash route without copying arbitrary query parameters.

- [ ] **Step 1: Replace navigation anchor targets**

For every cross-page link, replace patterns such as:

```html
href="../catalog/index.html" data-nav-target="../catalog/index.html"
```

with the matching route fallback and named target:

```html
href="/#/plugin-page/meme_manager_master/catalog"
data-nav-page="catalog"
```

Use the same mapping for `a_manage`, `catalog`, `settings`, and `semantic`. Keep visible labels and all unrelated attributes unchanged.

- [ ] **Step 2: Simplify the entry redirect**

Replace the entry script with a redirect to:

```js
window.location.replace("/#/plugin-page/meme_manager_master/a_manage");
```

Do not copy `window.location.search` into the target URL.

- [ ] **Step 3: Run focused static checks**

Run:

```powershell
python -m unittest tests.test_webui_navigation_auth -v
node --check pages/a_manage/api.js
node --check pages/a_manage/pack.js
node --check pages/catalog/script.js
node --check pages/settings/script.js
node --check pages/semantic/script.js
```

Expected: all tests and syntax checks pass.

- [ ] **Step 4: Commit the markup changes**

```powershell
git add pages/index.html pages/a_manage/index.html pages/catalog/index.html pages/settings/index.html pages/semantic/index.html
git commit -m "fix: navigate plugin pages through dashboard routes"
```

### Task 4: Full verification and handoff

**Files:**
- Test: `tests/` (read-only verification)
- Verify: `git diff --check`

**Interfaces:**
- No additional production interface; this task validates the completed navigation contract against the existing suite.

- [ ] **Step 1: Run the complete Python test suite**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass with no failures or errors.

- [ ] **Step 2: Run all page JavaScript syntax checks**

Run:

```powershell
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
```

Expected: every JavaScript file parses successfully.

- [ ] **Step 3: Check the patch for whitespace errors and stale token logic**

Run:

```powershell
git diff --check HEAD~3..HEAD
rg -n "asset_token|\.\./" pages tests/test_webui_navigation_auth.py
```

Expected: `git diff --check` is clean and the final search returns no navigation-related matches; any unrelated historical/documentation match must be investigated before handoff.

- [ ] **Step 4: Report the exact verification results**

Summarize changed files, test counts, syntax-check result, and the required AstrBot action: refresh the plugin page or reload the plugin so the Dashboard mounts a fresh Page and issues a new asset token.
