# 表情索引工作台页面内缩略图缓存 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让表情索引工作台在当前页面内复用已经成功加载的缩略图，使刷新、处置后的完整重绘和返回已浏览分页不再重复请求旧图片。

**Architecture:** 在两套原生工作台脚本中各维护一个成功结果 LRU Map 和一个进行中请求 Map。缩略图加载统一经过缓存层，原图预览继续直连现有接口；资源包切换、重索引完成和成功删除文件通过明确的失效入口处理，后端 API 保持不变。

**Tech Stack:** 原生 JavaScript、浏览器 Map/Promise、Python `unittest`、Node.js `vm` 运行时测试、AstrBot Plugin Page API。

## Global Constraints

- 缓存仅存在于当前页面生命周期；F5 或重新进入页面可重新加载全部缩略图。
- 成功缓存最多 512 项，并按 JavaScript 字符串每字符 2 字节估算限制为 64 MiB。
- 同一图片的进行中请求共享 Promise；失败和无效 Data URL 不缓存，点击重试必须重新请求。
- 缓存键包含资源包；合法 SHA-256 优先，否则使用相对路径，再回退到分类与文件名。
- 只缓存 `size: "preview"` 的缩略图；`size: "original"` 原图预览不缓存。
- 手动刷新、处置后的重绘、标签筛选和分页不清空；资源包切换和成功重索引清空；成功删除已整理/普通待分类文件逐项失效；重复记录忽略不逐项失效。
- 两套页面行为必须同步，但不得覆盖两者已有的导航差异。
- 更新两套脚本缓存版本和 `CHANGELOG.md` 的 `[Unreleased]`；不修改 `_conf_schema.json`、`metadata.yaml` 或插件版本。
- 所有实现使用现有 `apiGet`、`apiPost`、DOM 卡片状态和错误提示，不新增依赖或后端路由。

---

## 文件结构与职责

- `pages/semantic/script.js`：Dashboard 路由版工作台的页面级缓存、加载和失效逻辑。
- `pages/a_manage/semantic/script.js`：相对导航版工作台的同等缓存行为；保留文件开头现有导航差异。
- `pages/semantic/index.html`：更新第一套脚本缓存版本参数。
- `pages/a_manage/semantic/index.html`：更新第二套脚本缓存版本参数。
- `tests/test_capture_index_runtime.py`：用 Node DOM fake 统计真实缩略图请求，覆盖复用、重试、并发、失效和 LRU。
- `tests/test_capture_index_page.py`：锁定两套页面缓存常量、关键接口边界与相同缓存版本。
- `CHANGELOG.md`：记录用户可见的页面内缩略图复用优化和新鲜验证结果。

### Task 1: 缩略图成功缓存与进行中请求去重

**Files:**
- Modify: `tests/test_capture_index_runtime.py:129-490`
- Modify: `pages/semantic/script.js:38-275`
- Modify: `pages/a_manage/semantic/script.js:38-275`

**Interfaces:**
- Consumes: `getImageLocation(item) -> {managed_pack_id, category, filename} | null` 和 `apiGet("meme_image_data", params)`。
- Produces: `thumbnailCacheKey(item, location) -> string`、`getCachedThumbnail(item, location) -> Promise<string>`、`clearThumbnailCache() -> void`、`evictThumbnailFile(packId, filename) -> void`、`evictThumbnailItem(item, location?) -> void`，以及供 `loadThumbnail` 使用的成功 Data URL。

- [ ] **Step 1: 扩充 Node fake，写出会失败的请求复用测试**

在 `NODE_RUNTIME_HARNESS` 的 `runPage` 中加入请求计数和一次性失败状态，并让重索引状态只有在 POST 之后才返回完成，避免初始化时伪造一次重索引完成：

```javascript
let thumbnailCalls = 0;
let originalImageCalls = 0;
let thumbnailFailurePending = true;
let reindexStarted = false;

// apiGet 分支
if (endpoint === "meme_image_data") {
  if (params.size === "original") {
    originalImageCalls += 1;
    return { data_url: `data:image/png;base64,${Buffer.from(params.filename).toString("base64")}` };
  }
  thumbnailCalls += 1;
  if (params.filename === "meme_duplicate_c.png" && thumbnailFailurePending) {
    thumbnailFailurePending = false;
    throw new Error("thumbnail failed once");
  }
  return { data_url: `data:image/png;base64,${Buffer.from(params.filename).toString("base64")}` };
}
if (endpoint === "capture/reindex/status") {
  return reindexStarted
    ? { status: "completed", processed: 1, total: 1, message: "重索引已完成" }
    : { status: "idle", processed: 0, total: 0, message: "尚未重索引" };
}

// apiPost 分支
if (endpoint === "capture/reindex") {
  reindexStarted = true;
  return { status: "running", processed: 0, total: 1, message: "正在重索引" };
}
```

初始化完成后记录以下布尔结果并加入 Python 断言：初次渲染 52 张卡片只产生 51 次预览请求（两个相同 SHA-256 重复项共享一次请求）；失败卡片点击重试只增加一次并变为 `thumbnail-loaded`；点击“刷新记录”和标签筛选后调用数不增加；把现有成功删除场景移到首次翻页之前，删除 `meme_01.png` 后整页旧卡片命中缓存，仅补入 `meme_49.png` 增加一次；翻到第二页只为 `meme_50.png` 增加一次，返回第一页不增加。连续两次打开同一张卡片原图都必须增加 `originalImageCalls`，证明原图未进入缩略图缓存。

```javascript
const initialUniqueThumbnailRequests = thumbnailCalls === 51;
const retryCard = document.querySelector("#capture-pending-items").children[3];
const beforeRetry = thumbnailCalls;
await retryCard.children[0].dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const failedThumbnailRetried = thumbnailCalls === beforeRetry + 1 && retryCard.classList.contains("thumbnail-loaded");

const beforeRefresh = thumbnailCalls;
await document.querySelector("#capture-refresh-button").dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const manualRefreshReusedThumbnails = thumbnailCalls === beforeRefresh;

const beforeFilter = thumbnailCalls;
await document.querySelector("#capture-category-filters").children[1].dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const categoryFilterReusedThumbnails = thumbnailCalls === beforeFilter;

const beforeDelete = thumbnailCalls;
const successButton = document.querySelector("#capture-indexed-items").children[0].children[1].children[0];
const successDelete = successButton.dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
await document.querySelector("#capture-confirm-confirm").dispatch("click");
await successDelete;
await new Promise((resolve) => setImmediate(resolve));
const disposalLoadedOnlyRefill = thumbnailCalls === beforeDelete + 1;

const beforeNewPage = thumbnailCalls;
await document.querySelector("#capture-pagination-next").dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const newPageLoadedOnlyNewThumbnails = thumbnailCalls === beforeNewPage + 1;
await document.querySelector("#capture-pagination-prev").dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const returningPageReusedThumbnails = thumbnailCalls === beforeNewPage + 1;

const firstPreview = document.querySelector("#capture-indexed-items").children[0].children[0];
await firstPreview.dispatch("click");
await firstPreview.dispatch("click");
const originalPreviewStayedUncached = originalImageCalls === 2;
```

另在 fake 的 `Element` 上允许测试触发原生图片 `error` 事件。选择一张已经成功加载的卡片，派发其图片元素的 `error`，再点击卡片重试；断言 API 次数增加 1。该断言模拟“接口成功、浏览器解码失败”，防止坏 Data URL 留在成功缓存里：

```javascript
const decodeCard = document.querySelector("#capture-indexed-items").children[1];
const decodeImage = decodeCard.children[0].children[0].children[0];
const beforeDecodeRetry = thumbnailCalls;
await decodeImage.dispatch("error");
await decodeCard.dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const decodeFailureEvictedCache =
  thumbnailCalls === beforeDecodeRetry + 1 && decodeCard.classList.contains("thumbnail-loaded");
```

- [ ] **Step 2: 运行目标测试，确认 RED 来自重复请求**

Run: `python -m unittest tests.test_capture_index_runtime -v`

Expected: FAIL；`initialUniqueThumbnailRequests`、`manualRefreshReusedThumbnails`、`returningPageReusedThumbnails` 至少一项为 false，证明现有 `loadThumbnail` 会重复调用 API。

- [ ] **Step 3: 在两套脚本中加入相同的缓存核心**

在页面状态变量旁加入：

```javascript
const THUMBNAIL_CACHE_MAX_ENTRIES = 512;
const THUMBNAIL_CACHE_MAX_BYTES = 64 * 1024 * 1024;
const thumbnailCache = new Map();
const thumbnailRequests = new Map();
let thumbnailCacheBytes = 0;
```

在 `getImageLocation` 后加入以下完整职责的 helper；两套脚本使用相同函数名和数据结构：

```javascript
function thumbnailCacheKey(item, location) {
  const packId = String(location?.managed_pack_id || "").trim();
  if (!packId) return "";
  const digest = normalizeDigest(item?.sha256);
  if (digest) return JSON.stringify([packId, "sha256", digest]);
  const relativePath = String(item?.relative_path || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/, "");
  if (relativePath) return JSON.stringify([packId, "path", relativePath]);
  return JSON.stringify([packId, "location", location.category, location.filename]);
}

function removeThumbnailCacheEntry(key) {
  const entry = thumbnailCache.get(key);
  if (!entry) return;
  thumbnailCache.delete(key);
  thumbnailCacheBytes = Math.max(0, thumbnailCacheBytes - entry.bytes);
}

function trimThumbnailCache() {
  while (
    thumbnailCache.size > THUMBNAIL_CACHE_MAX_ENTRIES ||
    thumbnailCacheBytes > THUMBNAIL_CACHE_MAX_BYTES
  ) {
    const oldestKey = thumbnailCache.keys().next().value;
    if (oldestKey === undefined) break;
    removeThumbnailCacheEntry(oldestKey);
  }
}

function rememberThumbnail(key, dataUrl, location) {
  const bytes = dataUrl.length * 2;
  if (bytes > THUMBNAIL_CACHE_MAX_BYTES) return;
  removeThumbnailCacheEntry(key);
  const entry = {
    dataUrl,
    bytes,
    packId: location.managed_pack_id,
    filename: location.filename,
  };
  thumbnailCache.set(key, entry);
  thumbnailCacheBytes += entry.bytes;
  trimThumbnailCache();
}

function readThumbnailCache(key) {
  const entry = thumbnailCache.get(key);
  if (!entry) return "";
  thumbnailCache.delete(key);
  thumbnailCache.set(key, entry);
  return entry.dataUrl;
}

function clearThumbnailCache() {
  thumbnailCache.clear();
  thumbnailRequests.clear();
  thumbnailCacheBytes = 0;
}

function evictThumbnailFile(packId, filename) {
  for (const [key, entry] of thumbnailCache) {
    if (entry.packId === packId && entry.filename === filename) removeThumbnailCacheEntry(key);
  }
  for (const [key, request] of thumbnailRequests) {
    if (request.packId === packId && request.filename === filename) thumbnailRequests.delete(key);
  }
}

function evictThumbnailItem(item, location = getImageLocation(item)) {
  const key = location ? thumbnailCacheKey(item, location) : "";
  if (!key) return;
  removeThumbnailCacheEntry(key);
  thumbnailRequests.delete(key);
}

async function getCachedThumbnail(item, location) {
  const key = thumbnailCacheKey(item, location);
  if (!key) throw new Error("缩略图缓存键无效");
  const cached = readThumbnailCache(key);
  if (cached) return cached;
  const activeRequest = thumbnailRequests.get(key);
  if (activeRequest) return activeRequest.promise;

  const request = {
    packId: location.managed_pack_id,
    filename: location.filename,
    promise: null,
  };
  request.promise = (async () => {
    const data = await apiGet("meme_image_data", { ...location, size: "preview" });
    const dataUrl = String(data?.data_url || "");
    if (!/^data:image\/[a-z0-9.+-]+;base64,/i.test(dataUrl)) {
      throw new Error("缩略图数据为空或格式无效");
    }
    if (thumbnailRequests.get(key) === request) rememberThumbnail(key, dataUrl, location);
    return dataUrl;
  })().finally(() => {
    if (thumbnailRequests.get(key) === request) thumbnailRequests.delete(key);
  });
  thumbnailRequests.set(key, request);
  return request.promise;
}
```

将 `loadThumbnail` 中直接 `apiGet` 的代码替换为：

```javascript
const dataUrl = await getCachedThumbnail(item, location);
image.src = dataUrl;
```

并在创建卡片时保存 `const thumbnailLocation = getImageLocation(item);`，把缩略图元素的 `error` 监听器改为同时调用 `evictThumbnailItem(item, thumbnailLocation)` 和现有 `markThumbnailError(image, card)`，保证浏览器解码失败后点击重试会绕过坏缓存。显式传入渲染时的定位也避免资源包切换后，旧 DOM 的延迟 error 事件误删新资源包缓存。

保留 `showPreview` 的 `size: "original"` 请求不变。不要把两套脚本互相整文件覆盖，因为开头的导航逻辑不同。

- [ ] **Step 4: 运行运行时测试，确认 GREEN**

Run: `python -m unittest tests.test_capture_index_runtime -v`

Expected: PASS；两套页面均满足请求计数、失败重试和分页复用断言。

- [ ] **Step 5: 检查两套脚本语法并提交缓存核心**

Run:

```powershell
node --check pages/semantic/script.js
node --check pages/a_manage/semantic/script.js
python -m unittest discover -s tests -v
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
git diff --check
git add -- tests/test_capture_index_runtime.py pages/semantic/script.js pages/a_manage/semantic/script.js
git diff --cached --check
git commit -m "feat: cache capture thumbnails within page"
```

Expected: 两个 `node --check`、diff check 和测试均通过；commit 只含上述三个文件。

### Task 2: 精确失效、容量淘汰与脚本缓存版本

**Files:**
- Modify: `tests/test_capture_index_runtime.py:129-490`
- Modify: `tests/test_capture_index_page.py:128-187`
- Modify: `pages/semantic/script.js:140-170,434-480,706-718`
- Modify: `pages/a_manage/semantic/script.js:140-170,434-480,706-718`
- Modify: `pages/semantic/index.html:110`
- Modify: `pages/a_manage/semantic/index.html:110`

**Interfaces:**
- Consumes: Task 1 的 `clearThumbnailCache()`、`evictThumbnailFile(packId, filename)` 和 LRU 常量。
- Produces: 处置、资源包切换、重索引完成的缓存失效行为，以及两套页面统一脚本版本 `20260812-thumbnail-cache-1`。

- [ ] **Step 1: 写出失效和 LRU 的失败回归**

在运行时 harness 中追加以下状态验证：

- 成功删除 `meme_01.png` 后将同路径项目临时重新加入 `indexedAll`，刷新必须增加一次请求，随后移除该 fake 项恢复原工作流。
- 成功忽略 SHA-256 为 `a...a` 的重复记录后，加入一个新文件名但相同 SHA-256 的重复事件，刷新不得增加请求，证明只隐藏记录时保留内容缓存。
- 开始重索引前后比较 `thumbnailCalls`，完成后的工作区重绘必须重新请求当前可见图片。
- 将 pack select 改为 `other` 并触发 `change`，相同相对路径必须重新请求，证明资源包属于缓存身份且切包清空。
- 最后把 `indexedAll` 置空、`pendingAll` 换成 513 个唯一相对路径项目并刷新；再只保留第一个项目刷新，请求数必须增加 1，证明第一个 LRU 条目已按 512 项上限淘汰。
- 再把待处理项换成一个 `oversized.png`，让 fake 返回 `"data:image/png;base64," + "A".repeat(33 * 1024 * 1024)`；同一项目连续刷新时请求数必须再次增加 1，证明按 `dataUrl.length * 2` 估算后，超过 64 MiB 的条目不会滞留缓存。完成断言后立即清空 fake 数据引用，避免影响后续结果。
- 增加一个只在 `pack` 下延迟完成的 `deferred.png` 请求：请求发出后切到 `other`，再释放旧 Promise，最后切回 `pack`；`pack` 下同一图片必须再次请求，证明旧请求不会在 `clearThumbnailCache()` 后重新写回。

核心断言代码采用：

```javascript
const beforeReindexThumbnails = thumbnailCalls;
const reindexAction = document.querySelector("#capture-reindex-button").dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
await document.querySelector("#capture-confirm-confirm").dispatch("click");
await reindexAction;
await new Promise((resolve) => setImmediate(resolve));
const reindexClearedThumbnailCache = thumbnailCalls > beforeReindexThumbnails;

const beforePackSwitch = thumbnailCalls;
pack.value = "other";
await pack.dispatch("change");
await new Promise((resolve) => setImmediate(resolve));
const packSwitchClearedThumbnailCache = thumbnailCalls > beforePackSwitch;

pendingAll = Array.from({ length: 513 }, (_, index) => ({
  filename: `lru_${index}.png`,
  tag: "happy",
  category: "happy",
  relative_path: `memes/lru_${index}.png`,
  indexed: false,
}));
indexedAll = [];
await document.querySelector("#capture-refresh-button").dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const beforeLruProbe = thumbnailCalls;
pendingAll = [pendingAll[0]];
await document.querySelector("#capture-refresh-button").dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const lruEvictedOldestThumbnail = thumbnailCalls === beforeLruProbe + 1;

pendingAll = [{
  filename: "oversized.png",
  tag: "happy",
  category: "happy",
  relative_path: "memes/oversized.png",
  indexed: false,
}];
await document.querySelector("#capture-refresh-button").dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const beforeByteProbe = thumbnailCalls;
await document.querySelector("#capture-refresh-button").dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
const byteLimitEvictedOversizedThumbnail = thumbnailCalls === beforeByteProbe + 1;
```

延迟竞态使用显式 resolver：

```javascript
let resolveDeferredThumbnail;
let deferredPackRequests = 0;
// 将下列分支放在 apiGet 的 preview 计数之后、普通成功响应之前。
if (params.filename === "deferred.png" && params.managed_pack_id === "pack") {
  deferredPackRequests += 1;
  if (deferredPackRequests === 1) {
    return new Promise((resolve) => { resolveDeferredThumbnail = resolve; });
  }
}
pendingAll = [{
  filename: "deferred.png",
  tag: "happy",
  category: "happy",
  relative_path: "memes/deferred.png",
  indexed: false,
}];
const deferredRefresh = document.querySelector("#capture-refresh-button").dispatch("click");
await new Promise((resolve) => setImmediate(resolve));
pack.value = "other";
await pack.dispatch("change");
resolveDeferredThumbnail({ data_url: "data:image/png;base64,REVG" });
await deferredRefresh;
await new Promise((resolve) => setImmediate(resolve));
pack.value = "pack";
await pack.dispatch("change");
await new Promise((resolve) => setImmediate(resolve));
const staleRequestDidNotRepopulateCache = deferredPackRequests === 2;
```

在 `tests/test_capture_index_page.py` 新增 `test_thumbnail_cache_contract_and_asset_version_match`，对两套脚本断言包含：

```python
self.assertIn("THUMBNAIL_CACHE_MAX_ENTRIES = 512", script)
self.assertIn("THUMBNAIL_CACHE_MAX_BYTES = 64 * 1024 * 1024", script)
self.assertIn("dataUrl.length * 2", script)
self.assertIn("thumbnailRequests", script)
self.assertIn("if (shouldClearThumbnails) clearThumbnailCache();", script)
self.assertIn("evictThumbnailFile", script)
self.assertIn('if (item.kind !== "duplicate")', script)
self.assertIn('size: "original"', script)
self.assertIn('script.js?v=20260812-thumbnail-cache-1', source)
```

并把现有 `test_interaction_assets_use_a_fresh_cache_busting_version` 的两套期望版本同步改为 `20260812-thumbnail-cache-1`。

- [ ] **Step 2: 运行目标测试，确认 RED 来自缺少失效入口和旧资源版本**

Run: `python -m unittest tests.test_capture_index_runtime tests.test_capture_index_page -v`

Expected: FAIL；重索引/切包/LRU 或新脚本版本断言失败，且不是 Node 语法或测试 fake 错误。

- [ ] **Step 3: 接入三类失效规则**

在两套脚本的重索引完成分支中，必须先保留完成前状态，只有当前页面实际观察过 running 或主动发起过重索引时才清空，避免初始化读取历史 completed 状态造成无意义清空：

```javascript
if (state.status === "completed") {
  const shouldClearThumbnails = reindexing;
  reindexing = false;
  reindexButton.disabled = false;
  reindexButton.setAttribute("aria-busy", "false");
  if (shouldClearThumbnails) clearThumbnailCache();
  const refreshed = await loadWorkspace();
  if (refreshed) {
    notice.textContent = state.message || "重索引已完成";
    notice.classList.remove("error");
  }
  return;
}
```

在 `disposeCaptureItems` 请求前保存 `const disposalPackId = packSelect.value;`，成功结果循环中只对真实删除文件的 kind 失效：

```javascript
(result.succeeded || []).forEach((item) => {
  if (item.kind !== "duplicate") {
    evictThumbnailFile(disposalPackId, String(item.filename || ""));
  }
  const key = selectionKey(item);
  selectedItems.delete(key);
  failedDisposals.delete(key);
});
```

删除失败项不调用失效函数。重复项成功只隐藏事件、保留现有图片，也不调用逐项失效。

在 `packSelect` 的 `change` 监听器开头调用 `clearThumbnailCache()`，再执行现有停止轮询、清除筛选和加载工作区逻辑。`clearThumbnailCache` 删除进行中请求引用后，旧 Promise 的身份检查会阻止其完成时重新写回缓存。

- [ ] **Step 4: 更新两套 HTML 脚本版本**

把两处：

```html
<script type="module" src="./script.js?v=20260812-contextual-batch-1"></script>
```

替换为：

```html
<script type="module" src="./script.js?v=20260812-thumbnail-cache-1"></script>
```

CSS 未改，保留 `style.css?v=20260812-unified-disposal-1`。

- [ ] **Step 5: 运行目标测试和语法检查，确认 GREEN**

Run:

```powershell
python -m unittest tests.test_capture_index_runtime tests.test_capture_index_page -v
node --check pages/semantic/script.js
node --check pages/a_manage/semantic/script.js
python -m unittest discover -s tests -v
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
git diff --check
```

Expected: 所有目标测试通过；两套脚本语法通过；无空白错误。

- [ ] **Step 6: 提交失效和缓存版本改动**

Run:

```powershell
git add -- tests/test_capture_index_runtime.py tests/test_capture_index_page.py pages/semantic/script.js pages/a_manage/semantic/script.js pages/semantic/index.html pages/a_manage/semantic/index.html
git diff --cached --check
git diff --cached --stat
git commit -m "fix: invalidate capture thumbnail cache safely"
```

Expected: staged 文件仅为列出的六个文件；commit 成功。

### Task 3: 更新日志、完整门禁与最终交付提交

**Files:**
- Modify: `CHANGELOG.md:5-30`
- Delete after transferring execution results: `task_plan.md`
- Delete after transferring execution results: `findings.md`
- Delete after transferring execution results: `progress.md`

**Interfaces:**
- Consumes: Task 1 和 Task 2 已通过的页面行为与测试结果。
- Produces: `[Unreleased]` 用户可见变更记录、全量门禁证据和干净工作区。

- [ ] **Step 1: 更新 `[Unreleased]` 的用户可见变更**

在 `CHANGELOG.md` 的 `### 变更` 中加入：

```markdown
- 表情索引工作台现在会在当前页面内复用已经加载的缩略图；刷新记录、忽略或删除后的重绘、筛选以及返回已浏览分页时不再整批重复加载，只有首次出现的新图片需要请求。缓存随资源包切换、成功重索引或页面重新加载安全失效。
```

不要修改版本节、README 版本徽章、`metadata.yaml` 或 `_conf_schema.json`。

- [ ] **Step 2: 运行目标回归和全量验证门禁**

Run:

```powershell
python -m unittest tests.test_capture_index_runtime tests.test_capture_index_page -v
python -m unittest discover -s tests -v
Get-ChildItem pages -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName; if ($LASTEXITCODE -ne 0) { throw "node --check failed: $($_.FullName)" } }
python -m compileall -q .
python scripts/generate_conf_schema.py --check
python scripts/check_architecture.py
git diff --check
```

Expected: 目标和全量 unittest 通过（允许仓库既有、明确标记的兼容性 skip）；全部 JS、compileall、schema、架构和 diff check 返回 0。把本次全量 unittest 实际输出的通过/跳过数量写入 `CHANGELOG.md` 的 `### 验证`，替换旧的 325 项数字，不复用历史计数。

- [ ] **Step 3: 审阅产品 diff 和两套页面同步边界**

Run:

```powershell
git diff -- pages/semantic/script.js pages/a_manage/semantic/script.js
git diff -- pages/semantic/index.html pages/a_manage/semantic/index.html tests/test_capture_index_runtime.py tests/test_capture_index_page.py CHANGELOG.md
git status --short
```

Expected: 两套脚本的缓存 helper、失效调用和版本一致；文件间仅保留此前已有的导航/格式差异；没有调试输出、后端改动、配置改动或敏感路径。

- [ ] **Step 4: 清理本次代理的临时执行账本**

用 `apply_patch` 删除根目录中由本次任务创建的 `task_plan.md`、`findings.md` 和 `progress.md`。随后运行 `git status --short`，确认它们不再作为未跟踪文件出现，设计规格和实施计划继续保留在 `docs/superpowers/`。

- [ ] **Step 5: 提交 CHANGELOG 和最终必要修正**

Run:

```powershell
git add -- CHANGELOG.md
git diff --cached --check
git diff --cached
git commit -m "docs: record capture thumbnail cache optimization"
git status --short
```

Expected: commit 成功；工作区干净。若完整门禁期间产生必要代码修正，把对应源文件和测试明确加入本提交，并在提交前重新执行 Step 2 的完整门禁。

- [ ] **Step 6: AstrBot WebUI 人工验收说明**

在可访问真实 AstrBot WebUI 时检查：首次打开会加载可见缩略图；点击“刷新记录”不出现整页加载占位；忽略一张后旧卡片立即显示、仅补入的新卡片短暂加载；翻到第二页再返回第一页不重新加载；F5 后允许重新加载。若当前环境仍无法访问局域网 WebUI，在交付中明确标记为未验证，不得宣称人工验收通过。

## 完成标准

- 两套工作台在同一页面内复用成功缩略图且原图预览语义不变。
- 并发、失败、刷新、新卡片、返回分页、删除、重复忽略、切包、重索引和 LRU 上限都有运行时或静态回归。
- 所有项目门禁通过，`CHANGELOG.md` 使用新鲜测试计数，本地提交完成。
- 未经当前任务新的明确授权不执行 `git push`。
