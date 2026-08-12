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
    "capture-clear-selection-button", "capture-dispose-selected-button", "capture-selection-summary",
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
      if (endpoint === "meme_image_data") return { data_url: "data:image/png;base64,AA==" };
      if (endpoint === "capture/index/status") {
        indexStatusCalls += 1;
        return { status: "completed", processed: 1, total: 1, message: "分类索引已完成" };
      }
      if (endpoint === "capture/reindex/status") {
        return { status: "completed", processed: 1, total: 1, message: "重索引已完成" };
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
        const failed = disposePartially
          ? uniqueItems.filter((item) => item.kind === "indexed").map((item) => ({
              ...item,
              blacklisted: true,
              reason: "删除失败：locked",
            }))
          : [];
        const succeeded = disposePartially
          ? uniqueItems.filter((item) => item.kind !== "indexed")
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
      if (endpoint === "capture/reindex") return { status: "running", processed: 0, total: 1, message: "正在重索引" };
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
  const successButton = getDeleteButton();
  const successDelete = successButton.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await successDelete;
  await new Promise((resolve) => setImmediate(resolve));
  const deletePayload = calls.find((call) => call.endpoint === "capture/items/dispose").body;
  const successNotice = document.querySelector("#notice").textContent;
  const refilledAfterDelete = document.querySelector("#capture-indexed-items").children.length === 48 &&
    document.querySelector("#capture-indexed-items").children[47].children[0].children[1].textContent === "meme_49.png";

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
  disposePartially = true;
  const batchAction = document.querySelector("#capture-dispose-selected-button").dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await batchAction;
  await new Promise((resolve) => setImmediate(resolve));
  const disposeCalls = calls.filter((call) => call.endpoint === "capture/items/dispose");
  const batchPayload = disposeCalls[disposeCalls.length - 1].body;
  const partialFailureKeptSelected = document.querySelector("#capture-selection-summary").textContent.includes("已整理 1 张");
  const partialFailureMarkedCard = document.querySelector("#capture-indexed-items").children[0].className.includes("disposal-failed");
  return {
    deletePayload,
    clampPayload,
    successNotice,
    failureRestored,
    ignorePayload,
    batchPayload,
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
    selectedByCardClick,
    deselectedByCardClick,
    ignoreButtonDidNotSelect,
    workspacePages,
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
            self.assertEqual(payload["batchPayload"]["pack_id"], "pack")
            self.assertEqual(
                {item["kind"] for item in payload["batchPayload"]["items"]},
                {"indexed", "pending", "duplicate"},
            )
            self.assertTrue(payload["ignoredWithoutIndexedDelete"])
            self.assertTrue(payload["refilledAfterDelete"])
            self.assertTrue(payload["clampedAfterDelete"])
            self.assertTrue(payload["selectionPreservedOnPageTwo"])
            self.assertTrue(payload["crossPageSelectionPreserved"])
            self.assertTrue(payload["partialFailureKeptSelected"])
            self.assertTrue(payload["partialFailureMarkedCard"])
            self.assertTrue(payload["selectedByCardClick"])
            self.assertTrue(payload["deselectedByCardClick"])
            self.assertTrue(payload["ignoreButtonDidNotSelect"])
            self.assertIn("2", payload["workspacePages"])


if __name__ == "__main__":
    unittest.main()
