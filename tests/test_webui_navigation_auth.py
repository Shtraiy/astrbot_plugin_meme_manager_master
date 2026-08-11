import json
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class WebUINavigationAuthTests(unittest.TestCase):
    def test_pages_do_not_manually_forward_asset_tokens(self):
        sources = [
            ROOT / "pages" / "a_manage" / "api.js",
            ROOT / "pages" / "a_manage" / "catalog" / "script.js",
            ROOT / "pages" / "a_manage" / "settings" / "script.js",
            ROOT / "pages" / "a_manage" / "semantic" / "script.js",
            ROOT / "pages" / "catalog" / "script.js",
            ROOT / "pages" / "settings" / "script.js",
            ROOT / "pages" / "semantic" / "script.js",
        ]

        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("asset_token", source, str(path))

    def test_a_manage_page_links_use_in_frame_relative_paths(self):
        sources = [
            ROOT / "pages" / "a_manage" / "index.html",
            ROOT / "pages" / "a_manage" / "catalog" / "index.html",
            ROOT / "pages" / "a_manage" / "settings" / "index.html",
            ROOT / "pages" / "a_manage" / "semantic" / "index.html",
        ]

        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertIn("data-nav-page", source, str(path))
            self.assertNotIn('target="_top"', source, str(path))
            self.assertNotIn('href="/#/plugin-page/', source, str(path))

        manage_html = (ROOT / "pages" / "a_manage" / "index.html").read_text(
            encoding="utf-8"
        )
        for page_name in ("catalog", "settings", "semantic"):
            self.assertIn(
                f'href="./{page_name}/index.html"',
                manage_html,
            )

    def test_a_manage_navigation_runtime_stays_inside_sandbox(self):
        harness = textwrap.dedent(
            r'''
            const fs = require("fs");
            const vm = require("vm");

            class Link {
              constructor(pageName, href, view = "") {
                this.href = href;
                this.attributes = new Map([["data-nav-page", pageName], ["target", "_top"]]);
                if (view) this.attributes.set("data-nav-view", view);
              }
              getAttribute(name) { return this.attributes.get(name) ?? null; }
              removeAttribute(name) { this.attributes.delete(name); }
              get target() { return this.getAttribute("target") || ""; }
              set target(value) {
                if (value) this.attributes.set("target", String(value));
                else this.attributes.delete("target");
              }
            }

            const contentRoot =
              "http://astrbot.test/api/plugin/page/content/meme_manager_master/a_manage";
            const links = [
              new Link("semantic", `${contentRoot}/semantic/index.html?asset_token=short`),
              new Link("catalog", `${contentRoot}/catalog/index.html?asset_token=short`, "catalog"),
              new Link("settings", `${contentRoot}/settings/index.html?asset_token=short`),
            ];
            const window = {
              MemeManagerUI: {},
              location: {
                href: `${contentRoot}/index.html?managed_pack_id=pack-a&asset_token=current`,
                origin: "http://astrbot.test",
                search: "?managed_pack_id=pack-a&asset_token=current",
              },
            };
            const document = {
              querySelectorAll(selector) {
                return selector === "a[data-nav-page]" ? links : [];
              },
            };
            vm.runInNewContext(
              fs.readFileSync(process.argv[1], "utf8"),
              { window, document, URL, URLSearchParams },
            );
            window.MemeManagerUI.api.applySecureNavLinks();
            const result = Object.fromEntries(links.map((link) => {
              const parsed = new URL(link.href);
              return [link.getAttribute("data-nav-page"), {
                href: link.href,
                path: parsed.pathname,
                managed_pack_id: parsed.searchParams.get("managed_pack_id"),
                view: parsed.searchParams.get("view"),
                target: link.getAttribute("target"),
              }];
            }));
            process.stdout.write(JSON.stringify(result));
            '''
        )
        completed = subprocess.run(
            ["node", "-e", harness, str(ROOT / "pages" / "a_manage" / "api.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        result = json.loads(completed.stdout)

        self.assertEqual(
            result["semantic"],
            {
                "href": (
                    "http://astrbot.test/api/plugin/page/content/"
                    "meme_manager_master/a_manage/semantic/index.html"
                    "?asset_token=short&managed_pack_id=pack-a"
                ),
                "path": (
                    "/api/plugin/page/content/meme_manager_master/"
                    "a_manage/semantic/index.html"
                ),
                "managed_pack_id": "pack-a",
                "view": None,
                "target": None,
            },
        )
        self.assertEqual(result["catalog"]["view"], "catalog")
        self.assertEqual(result["catalog"]["managed_pack_id"], "pack-a")
        self.assertIsNone(result["settings"]["target"])
        self.assertNotIn(
            "plugin-page/meme_manager_master",
            result["settings"]["href"],
        )

    def test_nested_page_assets_are_copied_into_the_a_manage_scope(self):
        for page_name in ("catalog", "settings", "semantic"):
            page_root = ROOT / "pages" / "a_manage" / page_name
            self.assertTrue((page_root / "index.html").is_file(), page_name)
            self.assertTrue((page_root / "script.js").is_file(), page_name)
            self.assertTrue((page_root / "style.css").is_file(), page_name)

    def test_first_use_catalog_guide_reuses_rewritten_catalog_link(self):
        source = (ROOT / "pages" / "a_manage" / "pack.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('a[data-nav-page="catalog"]', source)
        self.assertNotIn("withCurrentPageParams", source)

    def test_pack_switch_refreshes_in_frame_navigation_params(self):
        source = (ROOT / "pages" / "a_manage" / "pack.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("window.history.replaceState", source)
        self.assertIn(
            "window.MemeManagerUI.api.applySecureNavLinks();",
            source,
        )

    def test_entry_redirect_does_not_copy_static_asset_token(self):
        source = (ROOT / "pages" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("asset_token", source)
        self.assertIn("plugin-page/meme_manager_master/a_manage", source)

    def test_capture_index_links_stay_inside_a_manage_page(self):
        html = (ROOT / "pages" / "a_manage" / "semantic" / "index.html").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "pages" / "a_manage" / "semantic" / "script.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('data-nav-page="a_manage"', html)
        self.assertIn('href="../index.html"', html)
        self.assertNotIn('target="_top"', html)
        self.assertNotIn('link.target = "_top"', script)
        self.assertNotIn("nextUrl.hash", script)
        self.assertNotIn("asset_token", script)

    def test_settings_assets_have_cache_busters_in_both_page_copies(self):
        for path in (
            ROOT / "pages" / "settings" / "index.html",
            ROOT / "pages" / "a_manage" / "settings" / "index.html",
        ):
            source = path.read_text(encoding="utf-8")
            self.assertRegex(source, r'./style\.css\?v=[^" ]+', str(path))
            self.assertRegex(source, r'./script\.js\?v=[^" ]+', str(path))

    def test_a_manage_navigation_scripts_have_fresh_cache_busters(self):
        pages = {
            ROOT / "pages" / "a_manage" / "index.html": "api.js",
            ROOT / "pages" / "a_manage" / "catalog" / "index.html": "script.js",
            ROOT / "pages" / "a_manage" / "settings" / "index.html": "script.js",
            ROOT / "pages" / "a_manage" / "semantic" / "index.html": "script.js",
        }

        for path, script_name in pages.items():
            source = path.read_text(encoding="utf-8")
            self.assertIn(
                f'{script_name}?v=20260811-sandbox-nav-fix-1',
                source,
                str(path),
            )


if __name__ == "__main__":
    unittest.main()
