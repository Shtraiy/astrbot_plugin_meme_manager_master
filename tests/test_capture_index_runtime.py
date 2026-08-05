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
    "capture-index-button", "capture-category-filters", "preview-mask",
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
    querySelectorAll() { return []; },
    addEventListener() {},
    createElement(tagName) { return new Element(tagName); },
  };
}

async function runPage(scriptPath) {
  const document = makeDocument();
  const calls = [];
  const workspace = {
    summary: { indexed: 1, pending: 1, duplicate: 0, complete_folders: 0, folder_total: 1 },
    folders: [{ category: "happy", tag: "happy", indexed: 1, total: 1, complete: true }],
    indexed_items: [{ filename: "meme_demo.png", tag: "happy", category: "happy", relative_path: "memes/meme_demo.png", indexed: true }],
    pending_items: [{ filename: "meme_pending.png", tag: "happy", category: "happy", relative_path: "memes/meme_pending.png", indexed: false }],
    library_index: { status: "idle", active_pack: true, message: "目录索引已加载" },
  };
  let deleteShouldFail = false;
  let workspaceCalls = 0;
  let indexStatusCalls = 0;
  const pageApi = {
    async ready() {},
    async apiGet(endpoint) {
      if (endpoint === "packs") return { packs: [{ id: "pack" }] };
      if (endpoint === "capture/workspace") {
        workspaceCalls += 1;
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

  const getDeleteButton = () => document.querySelector("#capture-indexed-items").children[0].children[1].children[0];
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
  return {
    deletePayload,
    successNotice,
    failureRestored,
    indexPayload,
    indexStatusCalls,
    workspaceCalls,
    reindexPayload,
    reindexRestored: !reindexButton.disabled && reindexButton.getAttribute("aria-busy") === "false",
    reindexNotice: document.querySelector("#notice").textContent,
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
            self.assertEqual(payload["workspaceCalls"], 6)
            self.assertEqual(payload["reindexPayload"]["pack_id"], "pack")
            self.assertTrue(payload["reindexRestored"])
            self.assertIn("重索引已完成", payload["reindexNotice"])


if __name__ == "__main__":
    unittest.main()
