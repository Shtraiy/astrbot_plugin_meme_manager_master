import json
import re
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages"
PAGE = PAGES / "a_manage"


class WebUiSpaContractTests(unittest.TestCase):
    def test_only_a_manage_is_discovered_as_a_business_page(self):
        business_pages = sorted(path.name for path in PAGES.iterdir() if path.is_dir())
        self.assertEqual(business_pages, ["a_manage"])

    def test_shell_contains_all_hash_views_and_loads_their_assets_up_front(self):
        source = (PAGE / "index.html").read_text(encoding="utf-8")

        for route in ("manage", "index", "settings"):
            self.assertIn(f'href="#{route}"', source)
            self.assertIn(f'data-view="{route}"', source)
        for asset in ("capture-index.css", "settings.css", "capture-index.js", "settings.js", "router.js"):
            self.assertIn(asset, source)

        self.assertNotIn("/index.html", source)
        self.assertNotIn("资源广场", source)

    def test_nested_html_pages_and_marketplace_assets_are_removed(self):
        for relative_path in (
            "catalog",
            "semantic",
            "settings",
            "../catalog",
            "../semantic",
            "../settings",
        ):
            self.assertFalse((PAGE / relative_path).exists(), relative_path)

    def test_navigation_never_reads_tokens_or_requests_another_html_document(self):
        sources = []
        for filename in ("api.js", "pack.js", "router.js", "capture-index.js", "settings.js"):
            path = PAGE / filename
            self.assertTrue(path.is_file(), filename)
            sources.append(path.read_text(encoding="utf-8"))

        combined = "\n".join(sources)
        self.assertNotIn("asset_token", combined)
        self.assertNotIn("/index.html", combined)
        self.assertNotIn("location.href =", combined)

    def test_router_preserves_query_and_initializes_each_view_only_once(self):
        harness = textwrap.dedent(
            r'''
            const fs = require("fs");
            const vm = require("vm");

            class Node {
              constructor(route = "") {
                this.dataset = route ? { route, view: route } : {};
                this.hidden = false;
                this.attributes = new Map();
              }
              setAttribute(name, value) { this.attributes.set(name, String(value)); }
              removeAttribute(name) { this.attributes.delete(name); }
            }

            const links = ["manage", "index", "settings"].map((route) => new Node(route));
            const views = ["manage", "index", "settings"].map((route) => new Node(route));
            const listeners = {};
            const calls = {
              manage: 0,
              index: 0,
              settings: 0,
              manageActivated: 0,
              indexActivated: 0,
              settingsActivated: 0,
            };
            let href = "http://astrbot.test/page?managed_pack_id=pack-a#unknown";
            const location = {
              get href() { return href; },
              get hash() { return new URL(href).hash; },
              set hash(value) { const url = new URL(href); url.hash = value; href = url.toString(); },
              get search() { return new URL(href).search; },
            };
            const window = {
              MemeManagerUI: {
                initManageView: async () => { calls.manage += 1; },
                initCaptureIndexView: async () => { calls.index += 1; },
                initSettingsView: async () => { calls.settings += 1; },
                activateManageView: async () => { calls.manageActivated += 1; },
                activateCaptureIndexView: async () => { calls.indexActivated += 1; },
                activateSettingsView: async () => { calls.settingsActivated += 1; },
              },
              location,
              history: {
                state: null,
                replaceState(_state, _title, nextHref) { href = new URL(nextHref, href).toString(); },
              },
              addEventListener(type, handler) { listeners[type] = handler; },
            };
            const document = {
              querySelectorAll(selector) {
                if (selector === "[data-route]") return links;
                if (selector === "[data-view]") return views;
                return [];
              },
              documentElement: { dataset: {} },
            };

            vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), { window, document, URL });
            (async () => {
              await window.MemeManagerUI.router.start();
              location.hash = "#settings";
              await listeners.hashchange();
              location.hash = "#manage";
              await listeners.hashchange();
              location.hash = "#settings";
              await listeners.hashchange();
              process.stdout.write(JSON.stringify({
                calls,
                href,
                visible: views.find((view) => !view.hidden).dataset.view,
                current: document.documentElement.dataset.currentView,
              }));
            })().catch((error) => {
              process.stderr.write(error.stack || String(error));
              process.exitCode = 1;
            });
            '''
        )
        completed = subprocess.run(
            ["node", "-e", harness, str(PAGE / "router.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["calls"],
            {
                "manage": 1,
                "index": 0,
                "settings": 1,
                "manageActivated": 2,
                "indexActivated": 0,
                "settingsActivated": 2,
            },
        )
        self.assertIn("managed_pack_id=pack-a", result["href"])
        self.assertTrue(result["href"].endswith("#settings"))
        self.assertEqual(result["visible"], "settings")
        self.assertEqual(result["current"], "settings")

    def test_batch_frontend_controls_and_state_are_removed(self):
        html = (PAGE / "index.html").read_text(encoding="utf-8")
        for identifier in (
            "batch-move-btn",
            "batch-delete-btn",
            "toggle-selection-mode-btn",
            "batch-context-menu",
            "move-target-modal",
            "capture-selection-mode-button",
            "capture-select-visible-duplicates-button",
            "capture-ignore-selected-button",
        ):
            self.assertNotIn(identifier, html)

        for filename in ("state.js", "emoji.js", "script.js", "capture-index.js"):
            source = (PAGE / filename).read_text(encoding="utf-8")
            self.assertNotIn("selectionState", source, filename)
            self.assertNotIn("selectedDuplicateDigests", source, filename)
            self.assertNotIn('"emoji/batch_delete"', source, filename)
            self.assertNotIn('"emoji/batch_copy"', source, filename)

        index_script = (PAGE / "capture-index.js").read_text(encoding="utf-8")
        self.assertIn('apiPost("capture/duplicates/ignore"', index_script)

    def test_settings_view_keeps_only_the_approved_core_modules(self):
        source = (PAGE / "index.html").read_text(encoding="utf-8")
        for identifier in (
            "rules-list",
            "save-rules-btn",
            "transfer-pack-select",
            "export-pack-download-btn",
            "pack-import-file",
            "export-backup-btn",
            "import-backup-btn",
            "log-list",
        ):
            self.assertIn(f'id="{identifier}"', source)

        self.assertNotIn("pack-import-overwrite-manual", source)
        self.assertNotIn("资源广场", source)

    def test_view_initializers_are_public_and_literal_dom_references_exist(self):
        html = (PAGE / "index.html").read_text(encoding="utf-8")
        html_ids = set(re.findall(r'id="([^"]+)"', html))
        initializers = {
            "script.js": ("initManageView", "activateManageView"),
            "capture-index.js": ("initCaptureIndexView", "activateCaptureIndexView"),
            "settings.js": ("initSettingsView", "activateSettingsView"),
        }

        for filename, (initializer, activator) in initializers.items():
            source = (PAGE / filename).read_text(encoding="utf-8")
            self.assertIn(f"window.MemeManagerUI.{initializer} = {initializer};", source)
            self.assertIn(f"window.MemeManagerUI.{activator} = {activator};", source)
            self.assertIn("InitializationPromise", source)
            referenced_ids = set(
                re.findall(r'document\.getElementById\(\s*"([^"]+)"', source)
            )
            self.assertEqual(referenced_ids - html_ids, set(), filename)

        state_source = (PAGE / "state.js").read_text(encoding="utf-8")
        state_ids = set(
            re.findall(r'document\.getElementById\(\s*"([^"]+)"', state_source)
        )
        self.assertEqual(state_ids - html_ids, set())

    def test_index_delete_refreshes_the_full_current_page(self):
        script = (PAGE / "capture-index.js").read_text(encoding="utf-8")
        delete_body = script.split("async function deleteIndexedItem", 1)[1].split(
            "function uniqueDuplicateDigests", 1
        )[0]
        self.assertIn("await loadWorkspace()", delete_body)
        self.assertNotIn("syncWorkspaceMetadata", delete_body)

    def test_single_pack_export_has_no_retired_mode_branch(self):
        html = (PAGE / "index.html").read_text(encoding="utf-8")
        script = (PAGE / "settings.js").read_text(encoding="utf-8")
        self.assertNotIn('name="export-mode"', html)
        self.assertNotIn("selectedExportMode", script)
        self.assertNotIn("updateExportModeAppearance", script)
        self.assertIn('mode: "share"', script)

    def test_index_pagination_sits_inside_indexed_panel_and_counts_only_indexed_items(self):
        html = (PAGE / "index.html").read_text(encoding="utf-8")
        indexed_items = html.index('id="capture-indexed-items"')
        pagination = html.index('id="capture-pagination"')
        pending_panel = html.index('id="capture-pending-panel"')
        self.assertLess(indexed_items, pagination)
        self.assertLess(pagination, pending_panel)

        script = (PAGE / "capture-index.js").read_text(encoding="utf-8")
        self.assertIn("Number(indexed.total || 0)", script)
        self.assertNotIn("pagination.pending.total", script)


if __name__ == "__main__":
    unittest.main()
