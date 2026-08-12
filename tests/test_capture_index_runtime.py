import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


NODE_RUNTIME_HARNESS = r'''
const fs = require("fs");
const vm = require("vm");

class ClassList {
  constructor() { this.values = new Set(); }
  add(...names) { names.forEach((name) => this.values.add(name)); }
  remove(...names) { names.forEach((name) => this.values.delete(name)); }
  contains(name) { return this.values.has(name); }
  toggle(name, force) {
    const shouldAdd = force === undefined ? !this.values.has(name) : Boolean(force);
    if (shouldAdd) this.values.add(name); else this.values.delete(name);
    return shouldAdd;
  }
}

class Element {
  constructor(tagName, id = "") {
    this.tagName = tagName;
    this.id = id;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.classList = new ClassList();
    this.dataset = {};
    this.value = "";
    this.disabled = false;
    this.hidden = false;
    this.textContent = "";
    this.innerHTML = "";
    this.parentElement = null;
  }
  append(...items) {
    for (const item of items) {
      if (item == null) continue;
      this.children.push(item);
      if (typeof item === "object") item.parentElement = this;
      if (this.tagName === "select" && !this.value && item.value) this.value = item.value;
    }
  }
  remove() {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
    this.parentElement = null;
  }
  querySelector(selector) {
    if (selector === ".card") {
      return this.children.find((child) => String(child.className || "").split(/\s+/).includes("card")) || null;
    }
    if (selector === ".card-preview") {
      return this.children.find((child) => String(child.className || "").split(/\s+/).includes("card-preview")) || null;
    }
    return null;
  }
  replaceChildren(...items) { this.children = []; this.append(...items); }
  addEventListener(type, handler) {
    (this.listeners[type] ||= []).push(handler);
  }
  async dispatch(type) {
    const event = { target: this, stopPropagation() {} };
    for (const handler of this.listeners[type] || []) await handler(event);
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  removeAttribute(name) { delete this.attributes[name]; }
  focus() {}
  scrollIntoView() {}
}

function makeDocument() {
  const ids = [
    "pack", "notice", "capture-summary", "capture-folders",
    "capture-indexed-items", "capture-pending-items", "capture-indexed-count",
    "capture-pending-count", "capture-refresh-button", "capture-reindex-button",
    "capture-reindex-progress", "capture-reindex-progress-label",
    "capture-reindex-progress-count", "capture-reindex-progress-bar",
    "capture-index-button", "capture-selection-mode-button", "capture-indexed-heading",
    "capture-select-indexed-page-button", "capture-select-pending-button",
    "capture-clear-selection-button", "capture-selection-summary",
    "capture-category-filters", "preview-mask",
    "capture-pagination", "capture-pagination-prev", "capture-pagination-pages",
    "capture-pagination-next", "capture-pagination-summary",
    "preview-image", "preview-close", "capture-confirm-mask",
    "capture-confirm-title", "capture-confirm-description",
    "capture-confirm-cancel", "capture-confirm-confirm",
  ];
  const elements = new Map(ids.map((id) => [id, new Element("div", id)]));
  const progressRow = new Element("div");
  elements.get("pack").tagName = "select";
  elements.get("capture-reindex-progress").classList.add("reindex-progress");
  elements.get("capture-reindex-progress").hidden = true;
  elements.get("capture-reindex-progress-bar").max = 1;
  elements.get("preview-mask").classList.add("hidden");
  return {
    querySelector(selector) {
      if (selector.startsWith("#")) return elements.get(selector.slice(1));
      if (selector === ".capture-progress-row") return progressRow;
      return null;
    },
    querySelectorAll(selector) {
      if (!selector.startsWith(".card")) return [];
      const results = [];
      const visit = (node) => {
        for (const child of node.children || []) {
          const classes = String(child.className || "").split(/\s+/);
          if (classes.includes("card") && (!selector.includes("[data-selection-key]") || child.dataset.selectionKey)) {
            results.push(child);
          }
          visit(child);
        }
      };
      for (const element of elements.values()) visit(element);
      return results;
    },
    addEventListener() {},
    createElement(tagName) { return new Element(tagName); },
  };
}

async function runPage(scriptPath) {
  const document = makeDocument();
  const calls = [];
  let indexedAll = Array.from({ length: 50 }, (_, index) => {
    const filename = `meme_${String(index + 1).padStart(2, "0")}.png`;
    return { filename, tag: "happy", category: "happy", relative_path: `memes/${filename}`, indexed: true };
  });
  let pendingAll = [
      { filename: "meme_pending.png", tag: "happy", category: "happy", relative_path: "memes/meme_pending.png", indexed: false },
      { filename: "meme_duplicate_a.png", tag: "happy", category: "happy", relative_path: "memes/meme_duplicate_a.png", indexed: false, duplicate: true, sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" },
      { filename: "meme_duplicate_b.png", tag: "sad", category: "sad", relative_path: "memes/meme_duplicate_b.png", indexed: false, duplicate: true, sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" },
      { filename: "meme_duplicate_c.png", tag: "happy", category: "happy", relative_path: "memes/meme_duplicate_c.png", indexed: false, duplicate: true, sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" },
  ];
  function workspaceFor(requestedPage) {
    const totalPages = Math.max(1, Math.ceil(indexedAll.length / 48));
    const page = Math.min(Math.max(1, Number(requestedPage || 1)), totalPages);
    const start = (page - 1) * 48;
    const duplicateDigests = [...new Set(pendingAll.filter((item) => item.duplicate).map((item) => item.sha256))];
    return {
      summary: {
        indexed: indexedAll.length,
        pending: pendingAll.filter((item) => !item.duplicate).length,
        duplicate: pendingAll.filter((item) => item.duplicate).length,
        complete_folders: 0,
        folder_total: 1,
      },
      folders: [{ category: "happy", tag: "happy", indexed: indexedAll.length, total: indexedAll.length, complete: true }],
      indexed_items: indexedAll.slice(start, start + 48),
      pending_items: pendingAll,
      pagination: {
        page,
        page_size: 48,
        indexed: { total: indexedAll.length, total_pages: totalPages },
        pending: { total: pendingAll.length, total_pages: 1 },
      },
      duplicate_digests: duplicateDigests,
      library_index: { status: "idle", active_pack: true, message: "目录索引已加载" },
    };
  }
  let disposeShouldFail = false;
  let disposePartially = false;
  let workspaceCalls = 0;
  let thumbnailCalls = 0;
  let originalImageCalls = 0;
  let thumbnailFailurePending = true;
  let reindexStarted = false;
  const workspacePages = [];
  let indexStatusCalls = 0;
  const pageApi = {
    async ready() {},
    async apiGet(endpoint, params = {}) {
      if (endpoint === "packs") return { packs: [{ id: "pack" }] };
      if (endpoint === "capture/workspace") {
        workspaceCalls += 1;
        workspacePages.push(String(params.page || "1"));
        return workspaceFor(params.page);
      }
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
      if (endpoint === "capture/index/status") {
        indexStatusCalls += 1;
        return { status: "completed", processed: 1, total: 1, message: "分类索引已完成" };
      }
      if (endpoint === "capture/reindex/status") {
        return reindexStarted
          ? { status: "completed", processed: 1, total: 1, message: "重索引已完成" }
          : { status: "idle", processed: 0, total: 0, message: "尚未重索引" };
      }
      throw new Error(`unexpected GET ${endpoint}`);
    },
    async apiPost(endpoint, body) {
      calls.push({ endpoint, body });
      if (endpoint === "capture/items/dispose") {
        if (disposeShouldFail) throw new Error("dispose failed");
        const uniqueItems = [...new Map(body.items.map((item) => [
          item.kind === "duplicate" ? `duplicate:${item.sha256}` : `${item.kind}:${item.filename}`,
          item,
        ])).values()];
        const failedItem = disposePartially
          ? uniqueItems.find((item) => item.kind === "indexed")
          : null;
        const failed = failedItem
          ? [{ ...failedItem, blacklisted: true, reason: "删除失败：locked" }]
          : [];
        const succeeded = failedItem
          ? uniqueItems.filter((item) => item !== failedItem)
          : uniqueItems;
        for (const item of succeeded) {
          if (item.kind === "indexed") indexedAll = indexedAll.filter((entry) => entry.filename !== item.filename);
          if (item.kind === "pending") pendingAll = pendingAll.filter((entry) => entry.filename !== item.filename);
          if (item.kind === "duplicate") pendingAll = pendingAll.filter((entry) => entry.sha256 !== item.sha256);
        }
        return {
          message: "统一处理完成",
          succeeded,
          failed,
          disposed_count: succeeded.length,
          failed_count: failed.length,
          blacklisted_count: uniqueItems.length,
        };
      }
      if (endpoint === "capture/index") return { status: "running", message: "分类索引已开始" };
      if (endpoint === "capture/reindex") {
        reindexStarted = true;
        return { status: "running", processed: 0, total: 1, message: "正在重索引" };
      }
      return { status: "ok" };
    },
  };
  globalThis.document = document;
  globalThis.window = { AstrBotPluginPage: pageApi, setTimeout, clearTimeout };
  const source = fs.readFileSync(scriptPath, "utf8").replace(
    "void initCaptureIndexPage();",
    "globalThis.pageInit = initCaptureIndexPage();",
  );
  vm.runInThisContext(source, { filename: scriptPath });
  await globalThis.pageInit;
  await new Promise((resolve) => setImmediate(resolve));
  const pack = document.querySelector("#pack");
  pack.value = "pack";

  const initialUniqueThumbnailRequests = thumbnailCalls === 51;
  const retryCard = document.querySelector("#capture-pending-items").children[3];
  const beforeRetry = thumbnailCalls;
  await retryCard.children[0].dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  const failedThumbnailRetried =
    thumbnailCalls === beforeRetry + 1 && retryCard.classList.contains("thumbnail-loaded");

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
  const deletePayload = calls.find((call) => call.endpoint === "capture/items/dispose").body;
  const successNotice = document.querySelector("#notice").textContent;
  const refilledAfterDelete = document.querySelector("#capture-indexed-items").children.length === 48 &&
    document.querySelector("#capture-indexed-items").children[47].children[0].children[1].textContent === "meme_49.png";
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

  const decodeCard = document.querySelector("#capture-indexed-items").children[1];
  const decodeImage = decodeCard.children[0].children[0].children[0];
  const beforeDecodeRetry = thumbnailCalls;
  await decodeImage.dispatch("error");
  await decodeCard.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  const decodeFailureEvictedCache =
    thumbnailCalls === beforeDecodeRetry + 1 && decodeCard.classList.contains("thumbnail-loaded");

  const duplicateCard = document.querySelector("#capture-pending-items").children[1];
  await document.querySelector("#capture-selection-mode-button").dispatch("click");
  await duplicateCard.dispatch("click");
  const selectedByCardClick = duplicateCard.classList.contains("selected");
  await duplicateCard.dispatch("click");
  const deselectedByCardClick = !duplicateCard.classList.contains("selected");
  const duplicateIgnoreButton = duplicateCard.children[1].children[0];
  await duplicateIgnoreButton.dispatch("click");
  await document.querySelector("#capture-confirm-cancel").dispatch("click");
  const ignoreButtonDidNotSelect = !duplicateCard.classList.contains("selected");

  const firstIndexedPreview = document.querySelector("#capture-indexed-items").children[0].children[0];
  await firstIndexedPreview.dispatch("click");
  await document.querySelector("#capture-pagination-next").dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  const selectionPreservedOnPageTwo = document.querySelector("#capture-selection-summary").textContent.includes("已整理 1 张");
  await document.querySelector("#capture-indexed-items").children[0].children[0].dispatch("click");
  await document.querySelector("#capture-pagination-prev").dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  const crossPageSelectionPreserved = document.querySelector("#capture-indexed-items").children[0].classList.contains("selected");
  await document.querySelector("#capture-clear-selection-button").dispatch("click");

  const getDeleteButton = () => document.querySelector("#capture-indexed-items").children[0].children[1].children[0];
  await document.querySelector("#capture-pagination-next").dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  const clampButton = getDeleteButton();
  const clampDelete = clampButton.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await clampDelete;
  await new Promise((resolve) => setImmediate(resolve));
  const clampPayload = calls.filter((call) => call.endpoint === "capture/items/dispose")[1].body;
  const clampedAfterDelete = document.querySelector("#capture-pagination-summary").textContent.includes("第 1/1 页") &&
    document.querySelector("#capture-indexed-items").children.length === 48;

  disposeShouldFail = true;
  const failureButton = getDeleteButton();
  const failedDelete = failureButton.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await failedDelete;
  await new Promise((resolve) => setImmediate(resolve));
  const failureRestored = !failureButton.disabled && failureButton.getAttribute("aria-busy") === "false";

  disposeShouldFail = false;
  const getIgnoreButton = () => document.querySelector("#capture-pending-items").children[1].children[1].children[0];
  const ignoreButton = getIgnoreButton();
  const ignoreAction = ignoreButton.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await ignoreAction;
  await new Promise((resolve) => setImmediate(resolve));
  const ignorePayload = calls.find((call) =>
    call.endpoint === "capture/items/dispose" && call.body.items[0]?.kind === "duplicate"
  ).body;
  const ignoredWithoutIndexedDelete = indexedAll.length === 48;

  const indexAction = document.querySelector("#capture-index-button").dispatch("click");
  await indexAction;
  await new Promise((resolve) => setImmediate(resolve));
  const indexPayload = calls.find((call) => call.endpoint === "capture/index").body;

  const reindexAction = document.querySelector("#capture-reindex-button").dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await reindexAction;
  await new Promise((resolve) => setImmediate(resolve));
  const reindexPayload = calls.find((call) => call.endpoint === "capture/reindex").body;
  const reindexButton = document.querySelector("#capture-reindex-button");
  const reindexNotice = document.querySelector("#notice").textContent;

  await document.querySelector("#capture-selection-mode-button").dispatch("click");
  await document.querySelector("#capture-select-pending-button").dispatch("click");
  await document.querySelector("#capture-indexed-items").children[0].children[0].dispatch("click");
  await document.querySelector("#capture-indexed-items").children[1].children[0].dispatch("click");

  const unselectedIndexedAction = document.querySelector("#capture-indexed-items").children[2].children[1].children[0].dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await unselectedIndexedAction;
  await new Promise((resolve) => setImmediate(resolve));
  let disposeCalls = calls.filter((call) => call.endpoint === "capture/items/dispose");
  const unselectedIndexedPayload = disposeCalls[disposeCalls.length - 1].body;
  const selectionsPreservedAfterUnselectedAction =
    document.querySelector("#capture-selection-summary").textContent.includes("已整理 2 张") &&
    document.querySelector("#capture-selection-summary").textContent.includes("待处理 2 张");

  disposePartially = true;
  const indexedBatchAction = document.querySelector("#capture-indexed-items").children[0].children[1].children[0].dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await indexedBatchAction;
  await new Promise((resolve) => setImmediate(resolve));
  disposeCalls = calls.filter((call) => call.endpoint === "capture/items/dispose");
  const indexedBatchPayload = disposeCalls[disposeCalls.length - 1].body;
  const pendingSelectionPreservedAfterIndexedBatch = document.querySelector("#capture-selection-summary").textContent.includes("待处理 2 张");
  const partialFailureKeptSelected = document.querySelector("#capture-selection-summary").textContent.includes("已整理 1 张");
  const partialFailureMarkedCard = document.querySelector("#capture-indexed-items").children[0].className.includes("disposal-failed");
  const partialFailureCardStayedSelected = document.querySelector("#capture-indexed-items").children[0].classList.contains("selected");

  disposePartially = false;
  const pendingBatchAction = document.querySelector("#capture-pending-items").children[0].children[1].children[0].dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await pendingBatchAction;
  await new Promise((resolve) => setImmediate(resolve));
  disposeCalls = calls.filter((call) => call.endpoint === "capture/items/dispose");
  const pendingBatchPayload = disposeCalls[disposeCalls.length - 1].body;
  const indexedSelectionPreservedAfterPendingBatch = document.querySelector("#capture-selection-summary").textContent.includes("已整理 1 张");
  const pendingSelectionClearedAfterPendingBatch = document.querySelector("#capture-selection-summary").textContent.includes("待处理 0 张");
  return {
    deletePayload,
    clampPayload,
    successNotice,
    failureRestored,
    ignorePayload,
    unselectedIndexedPayload,
    selectionsPreservedAfterUnselectedAction,
    indexedBatchPayload,
    pendingBatchPayload,
    pendingSelectionPreservedAfterIndexedBatch,
    indexedSelectionPreservedAfterPendingBatch,
    pendingSelectionClearedAfterPendingBatch,
    ignoredWithoutIndexedDelete,
    indexPayload,
    indexStatusCalls,
    workspaceCalls,
    reindexPayload,
    reindexRestored: !reindexButton.disabled && reindexButton.getAttribute("aria-busy") === "false",
    reindexNotice,
    refilledAfterDelete,
    clampedAfterDelete,
    selectionPreservedOnPageTwo,
    crossPageSelectionPreserved,
    partialFailureKeptSelected,
    partialFailureMarkedCard,
    partialFailureCardStayedSelected,
    selectedByCardClick,
    deselectedByCardClick,
    ignoreButtonDidNotSelect,
    workspacePages,
    initialUniqueThumbnailRequests,
    failedThumbnailRetried,
    manualRefreshReusedThumbnails,
    categoryFilterReusedThumbnails,
    disposalLoadedOnlyRefill,
    newPageLoadedOnlyNewThumbnails,
    returningPageReusedThumbnails,
    originalPreviewStayedUncached,
    decodeFailureEvictedCache,
  };
}

(async () => {
  const results = {};
  for (const scriptPath of process.argv.slice(1)) results[scriptPath] = await runPage(scriptPath);
  process.stdout.write(JSON.stringify(results));
})().catch((error) => {
  process.stderr.write(error.stack || String(error));
  process.exitCode = 1;
});
'''


NODE_CACHE_BOUNDARY_HARNESS = NODE_RUNTIME_HARNESS.split("async function runPage(scriptPath) {", 1)[0] + r'''
function settle() {
  return new Promise((resolve) => setImmediate(() => setImmediate(resolve)));
}

async function runThumbnailCacheScenario(scriptPath, options = {}) {
  const document = makeDocument();
  const callsByFilename = new Map();
  const items = ["a", "b", "c", "oversize", "invalid"].map((category) => ({
    filename: `${category}.png`,
    tag: category,
    category,
    relative_path: `memes/${category}.png`,
    indexed: true,
  }));
  const pageApi = {
    async ready() {},
    async apiGet(endpoint, params = {}) {
      if (endpoint === "packs") return { packs: [{ id: "pack" }] };
      if (endpoint === "capture/workspace") {
        const category = String(params.category || "");
        return {
          summary: { indexed: items.length, pending: 0, duplicate: 0, complete_folders: 0, folder_total: items.length },
          folders: items.map((item) => ({ category: item.category, tag: item.tag, indexed: 1, total: 1, complete: true })),
          indexed_items: category ? items.filter((item) => item.category === category) : [],
          pending_items: [],
          pagination: { page: 1, indexed: { total: category ? 1 : 0, total_pages: 1 }, pending: { total: 0, total_pages: 1 } },
          library_index: { status: "idle", active_pack: true, message: "目录索引已加载" },
        };
      }
      if (endpoint === "meme_image_data") {
        const filename = String(params.filename || "");
        callsByFilename.set(filename, (callsByFilename.get(filename) || 0) + 1);
        if (filename === "invalid.png") return { data_url: "invalid-data-url" };
        if (filename === "oversize.png") return { data_url: `data:image/png;base64,${"A".repeat(300)}` };
        return { data_url: `data:image/png;base64,${Buffer.from(filename).toString("base64")}` };
      }
      if (endpoint === "capture/reindex/status") return { status: "idle", processed: 0, total: 0, message: "尚未重索引" };
      if (endpoint === "capture/index/status") return { status: "idle", processed: 0, total: 0, message: "尚未索引" };
      throw new Error(`unexpected GET ${endpoint}`);
    },
    async apiPost() { return { status: "ok" }; },
  };
  globalThis.document = document;
  globalThis.window = { AstrBotPluginPage: pageApi, setTimeout, clearTimeout };
  let source = fs.readFileSync(scriptPath, "utf8")
    .replace("const THUMBNAIL_CACHE_MAX_ENTRIES = 512;", `const THUMBNAIL_CACHE_MAX_ENTRIES = ${options.entries};`)
    .replace("const THUMBNAIL_CACHE_MAX_BYTES = 64 * 1024 * 1024;", `const THUMBNAIL_CACHE_MAX_BYTES = ${options.bytes};`)
    .replace("void initCaptureIndexPage();", "globalThis.pageInit = initCaptureIndexPage();");
  if (options.mutateReadDoesNotRefreshLru) {
    source = source.replace(
      "thumbnailCache.delete(key);\n    thumbnailCache.set(key, entry);",
      "// deliberate mutation: cache hits do not refresh recency",
    );
  }
  if (options.mutateAcceptInvalidDataUrl) {
    source = source.replace(
      "if (!/^data:image\\/[a-z0-9.+-]+;base64,/i.test(dataUrl)) {",
      "if (false) {",
    );
  }
  vm.runInThisContext(source, { filename: scriptPath });
  await globalThis.pageInit;
  await settle();

  const selectCategory = async (index) => {
    await document.querySelector("#capture-category-filters").children[index].dispatch("click");
    await settle();
  };
  for (const index of options.sequence || [1, 2, 1, 3, 2]) await selectCategory(index);
  const entryLruEviction =
    callsByFilename.get("a.png") === 1 && callsByFilename.get("b.png") === 2 && callsByFilename.get("c.png") === 1;

  return { entryLruEviction, callsByFilename: Object.fromEntries(callsByFilename) };
}

async function runThumbnailCacheBoundaries(scriptPath, mutations = {}) {
  const entry = await runThumbnailCacheScenario(scriptPath, {
    entries: 2,
    bytes: 10000,
    mutateReadDoesNotRefreshLru: mutations.readDoesNotRefreshLru,
    sequence: [1, 2, 1, 3, 2],
  });
  const byte = await runThumbnailCacheScenario(scriptPath, {
    entries: 10,
    bytes: 130,
    sequence: [1, 2, 3, 2, 1],
  });
  const byteCalls = byte.callsByFilename;
  const byteEvictionKeepsRemainingEntry =
    byteCalls["a.png"] === 2 && byteCalls["b.png"] === 1 && byteCalls["c.png"] === 1;

  const oversized = await runThumbnailCacheScenario(scriptPath, {
    entries: 10,
    bytes: 130,
    sequence: [4, 4],
  });
  const oversizedCalls = oversized.callsByFilename;
  const oversizedThumbnailIsNotCached = oversizedCalls["oversize.png"] === 2;

  const invalid = await runThumbnailCacheScenario(scriptPath, {
    entries: 10,
    bytes: 130,
    sequence: [5, 5],
    mutateAcceptInvalidDataUrl: mutations.acceptInvalidDataUrl,
  });
  const invalidCalls = invalid.callsByFilename;
  const invalidDataUrlIsNotCached = invalidCalls["invalid.png"] === 2;
  return {
    entryLruEviction: entry.entryLruEviction,
    byteEvictionKeepsRemainingEntry,
    oversizedThumbnailIsNotCached,
    invalidDataUrlIsNotCached,
  };
}

(async () => {
  const scripts = process.argv.slice(1);
  const actual = {};
  for (const scriptPath of scripts) actual[scriptPath] = await runThumbnailCacheBoundaries(scriptPath);
  const mutatedReadDoesNotRefreshLru = await runThumbnailCacheBoundaries(scripts[0], {
    readDoesNotRefreshLru: true,
  });
  const mutatedAcceptInvalidDataUrl = await runThumbnailCacheBoundaries(scripts[0], {
    acceptInvalidDataUrl: true,
  });
  process.stdout.write(JSON.stringify({ actual, mutatedReadDoesNotRefreshLru, mutatedAcceptInvalidDataUrl }));
})().catch((error) => {
  process.stderr.write(error.stack || String(error));
  process.exitCode = 1;
});
'''


class CaptureIndexRuntimeTests(unittest.TestCase):
    def test_delete_and_reindex_runtime_states_for_both_page_copies(self):
        scripts = [
            str(ROOT / "pages" / "semantic" / "script.js"),
            str(ROOT / "pages" / "a_manage" / "semantic" / "script.js"),
        ]
        result = subprocess.run(
            ["node", "-e", NODE_RUNTIME_HARNESS, *scripts],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payloads = json.loads(result.stdout)
        for payload in payloads.values():
            self.assertEqual(payload["deletePayload"]["pack_id"], "pack")
            self.assertEqual(
                payload["deletePayload"]["items"],
                [{"kind": "indexed", "filename": "meme_01.png"}],
            )
            self.assertIn("统一处理完成", payload["successNotice"])
            self.assertEqual(
                payload["clampPayload"]["items"],
                [{"kind": "indexed", "filename": "meme_50.png"}],
            )
            self.assertTrue(payload["failureRestored"])
            self.assertEqual(payload["indexPayload"]["pack_id"], "pack")
            self.assertEqual(payload["indexStatusCalls"], 1)
            self.assertGreaterEqual(payload["workspaceCalls"], 9)
            self.assertEqual(payload["reindexPayload"]["pack_id"], "pack")
            self.assertTrue(payload["reindexRestored"])
            self.assertIn("重索引已完成", payload["reindexNotice"])
            self.assertEqual(payload["ignorePayload"]["pack_id"], "pack")
            self.assertEqual(
                payload["ignorePayload"]["items"],
                [{
                    "kind": "duplicate",
                    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                }],
            )
            self.assertEqual(payload["indexedBatchPayload"]["pack_id"], "pack")
            self.assertEqual(
                payload["unselectedIndexedPayload"]["items"],
                [{"kind": "indexed", "filename": "meme_04.png"}],
            )
            self.assertTrue(payload["selectionsPreservedAfterUnselectedAction"])
            self.assertEqual(
                {item["kind"] for item in payload["indexedBatchPayload"]["items"]},
                {"indexed"},
            )
            self.assertEqual(
                {item["filename"] for item in payload["indexedBatchPayload"]["items"]},
                {"meme_02.png", "meme_03.png"},
            )
            self.assertEqual(payload["pendingBatchPayload"]["pack_id"], "pack")
            self.assertEqual(
                {item["kind"] for item in payload["pendingBatchPayload"]["items"]},
                {"pending", "duplicate"},
            )
            self.assertNotIn(
                "indexed",
                {item["kind"] for item in payload["pendingBatchPayload"]["items"]},
            )
            self.assertTrue(payload["pendingSelectionPreservedAfterIndexedBatch"])
            self.assertTrue(payload["indexedSelectionPreservedAfterPendingBatch"])
            self.assertTrue(payload["pendingSelectionClearedAfterPendingBatch"])
            self.assertTrue(payload["ignoredWithoutIndexedDelete"])
            self.assertTrue(payload["refilledAfterDelete"])
            self.assertTrue(payload["clampedAfterDelete"])
            self.assertTrue(payload["selectionPreservedOnPageTwo"])
            self.assertTrue(payload["crossPageSelectionPreserved"])
            self.assertTrue(payload["partialFailureKeptSelected"])
            self.assertTrue(payload["partialFailureMarkedCard"])
            self.assertTrue(payload["partialFailureCardStayedSelected"])
            self.assertTrue(payload["selectedByCardClick"])
            self.assertTrue(payload["deselectedByCardClick"])
            self.assertTrue(payload["ignoreButtonDidNotSelect"])
            self.assertIn("2", payload["workspacePages"])
            self.assertTrue(payload["initialUniqueThumbnailRequests"])
            self.assertTrue(payload["failedThumbnailRetried"])
            self.assertTrue(payload["manualRefreshReusedThumbnails"])
            self.assertTrue(payload["categoryFilterReusedThumbnails"])
            self.assertTrue(payload["disposalLoadedOnlyRefill"])
            self.assertTrue(payload["newPageLoadedOnlyNewThumbnails"])
            self.assertTrue(payload["returningPageReusedThumbnails"])
            self.assertTrue(payload["originalPreviewStayedUncached"])
            self.assertTrue(payload["decodeFailureEvictedCache"])

    def test_thumbnail_cache_boundaries_for_both_page_copies(self):
        scripts = [
            str(ROOT / "pages" / "semantic" / "script.js"),
            str(ROOT / "pages" / "a_manage" / "semantic" / "script.js"),
        ]
        result = subprocess.run(
            ["node", "-e", NODE_CACHE_BOUNDARY_HARNESS, *scripts],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payloads = json.loads(result.stdout)
        for payload in payloads["actual"].values():
            self.assertTrue(payload["entryLruEviction"])
            self.assertTrue(payload["byteEvictionKeepsRemainingEntry"])
            self.assertTrue(payload["oversizedThumbnailIsNotCached"])
            self.assertTrue(payload["invalidDataUrlIsNotCached"])
        self.assertFalse(payloads["mutatedReadDoesNotRefreshLru"]["entryLruEviction"])
        self.assertFalse(payloads["mutatedAcceptInvalidDataUrl"]["invalidDataUrlIsNotCached"])


if __name__ == "__main__":
    unittest.main()
