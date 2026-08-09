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
}

function makeDocument() {
  const ids = [
    "pack", "notice", "capture-summary", "capture-folders",
    "capture-indexed-items", "capture-pending-items", "capture-indexed-count",
    "capture-pending-count", "capture-refresh-button", "capture-reindex-button",
    "capture-reindex-progress", "capture-reindex-progress-label",
    "capture-reindex-progress-count", "capture-reindex-progress-bar",
    "capture-index-button", "capture-ignore-duplicates-button", "capture-selection-mode-button",
    "capture-select-visible-duplicates-button", "capture-ignore-selected-button", "capture-selection-summary",
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
          if (classes.includes("card") && (!selector.includes("[data-sha256]") || child.dataset.sha256)) {
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
  const workspace = {
     summary: { indexed: 2, pending: 1, duplicate: 3, complete_folders: 0, folder_total: 1 },
     folders: [{ category: "happy", tag: "happy", indexed: 2, total: 2, complete: true }],
     indexed_items: [
       { filename: "meme_demo.png", tag: "happy", category: "happy", relative_path: "memes/meme_demo.png", indexed: true },
       { filename: "meme_demo_two.png", tag: "happy", category: "happy", relative_path: "memes/meme_demo_two.png", indexed: true },
     ],
     pending_items: [
      { filename: "meme_pending.png", tag: "happy", category: "happy", relative_path: "memes/meme_pending.png", indexed: false },
      { filename: "meme_duplicate_a.png", tag: "happy", category: "happy", relative_path: "memes/meme_duplicate_a.png", indexed: false, duplicate: true, sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" },
      { filename: "meme_duplicate_b.png", tag: "sad", category: "sad", relative_path: "memes/meme_duplicate_b.png", indexed: false, duplicate: true, sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" },
       { filename: "meme_duplicate_c.png", tag: "happy", category: "happy", relative_path: "memes/meme_duplicate_c.png", indexed: false, duplicate: true, sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" },
     ],
     pagination: {
       page: 1,
       page_size: 48,
       indexed: { total: 49, total_pages: 2 },
       pending: { total: 4, total_pages: 1 },
     },
     duplicate_digests: ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"],
    library_index: { status: "idle", active_pack: true, message: "目录索引已加载" },
  };
  let deleteShouldFail = false;
  let ignoreShouldFail = false;
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
        if (String(params.page || "1") === "2") {
          return {
            ...workspace,
            indexed_items: [{ filename: "meme_page_two.png", tag: "happy", category: "happy", relative_path: "memes/meme_page_two.png", indexed: true }],
            pending_items: [],
            pagination: {
              page: 2,
              page_size: 48,
              indexed: { total: 49, total_pages: 2 },
              pending: { total: 4, total_pages: 1 },
            },
          };
        }
        return workspace;
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
      if (endpoint === "emoji/delete" && deleteShouldFail) throw new Error("delete failed");
      if (endpoint === "capture/duplicates/ignore" && ignoreShouldFail) throw new Error("ignore failed");
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
  const pack = document.querySelector("#pack");
  pack.value = "pack";

   const getDeleteButton = () => document.querySelector("#capture-indexed-items").children[0].children[2].children[0];
  const successButton = getDeleteButton();
  const successDelete = successButton.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await successDelete;
  await new Promise((resolve) => setImmediate(resolve));
  const deletePayload = calls.find((call) => call.endpoint === "emoji/delete").body;
  const successNotice = document.querySelector("#notice").textContent;

  deleteShouldFail = true;
  const failureButton = getDeleteButton();
  const failedDelete = failureButton.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await failedDelete;
  await new Promise((resolve) => setImmediate(resolve));
  const failureRestored = !failureButton.disabled && failureButton.getAttribute("aria-busy") === "false";

   const getIgnoreButton = () => document.querySelector("#capture-pending-items").children[1].children[2].children[0];
  const ignoreButton = getIgnoreButton();
  const ignoreAction = ignoreButton.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await ignoreAction;
  const ignorePayload = calls.find((call) => call.endpoint === "capture/duplicates/ignore").body;
  const ignoredWithoutDelete = !calls.some((call) => call.endpoint === "emoji/delete" && call.body.image_file === "meme_duplicate_a.png");

  ignoreShouldFail = true;
  const failedIgnore = getIgnoreButton();
  const failedIgnoreAction = failedIgnore.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await failedIgnoreAction;
  const ignoreFailureRestored = !failedIgnore.disabled && failedIgnore.getAttribute("aria-busy") === "false";
  ignoreShouldFail = false;

  const bulkAction = document.querySelector("#capture-ignore-duplicates-button").dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  await document.querySelector("#capture-confirm-confirm").dispatch("click");
  await bulkAction;
  const ignoreCalls = calls.filter((call) => call.endpoint === "capture/duplicates/ignore");
  const bulkPayload = ignoreCalls[ignoreCalls.length - 1].body;

  deleteShouldFail = false;
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
  const paginationAction = document.querySelector("#capture-pagination-next").dispatch("click");
  await paginationAction;
  await new Promise((resolve) => setImmediate(resolve));
  const pageTwoRendered = document.querySelector("#capture-indexed-items").children[0].children[1].children[1].textContent === "meme_page_two.png";
  return {
    deletePayload,
    successNotice,
    failureRestored,
    ignorePayload,
    bulkPayload,
    ignoredWithoutDelete,
    ignoreFailureRestored,
    indexPayload,
    indexStatusCalls,
    workspaceCalls,
    reindexPayload,
    reindexRestored: !reindexButton.disabled && reindexButton.getAttribute("aria-busy") === "false",
    reindexNotice,
    pageTwoRendered,
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
            self.assertEqual(payload["deletePayload"]["managed_pack_id"], "pack")
            self.assertEqual(payload["deletePayload"]["image_file"], "meme_demo.png")
            self.assertIn("已删除", payload["successNotice"])
            self.assertTrue(payload["failureRestored"])
            self.assertEqual(payload["indexPayload"]["pack_id"], "pack")
            self.assertEqual(payload["indexStatusCalls"], 1)
            self.assertEqual(payload["workspaceCalls"], 9)
            self.assertEqual(payload["reindexPayload"]["pack_id"], "pack")
            self.assertTrue(payload["reindexRestored"])
            self.assertIn("重索引已完成", payload["reindexNotice"])
            self.assertEqual(payload["ignorePayload"]["pack_id"], "pack")
            self.assertEqual(
                payload["ignorePayload"]["sha256s"],
                ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
            )
            self.assertEqual(payload["bulkPayload"]["pack_id"], "pack")
            self.assertEqual(
                payload["bulkPayload"]["sha256s"],
                [
                    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                ],
            )
            self.assertTrue(payload["ignoredWithoutDelete"])
            self.assertTrue(payload["ignoreFailureRestored"])
            self.assertTrue(payload["pageTwoRendered"])
            self.assertEqual(payload["workspacePages"][-1], "2")


if __name__ == "__main__":
    unittest.main()
