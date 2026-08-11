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
            self.assertIn("plugin-page/meme_manager_master", source, str(path))

    def test_page_links_use_dashboard_targets_instead_of_relative_paths(self):
        sources = [
            ROOT / "pages" / "a_manage" / "index.html",
            ROOT / "pages" / "a_manage" / "catalog" / "index.html",
            ROOT / "pages" / "a_manage" / "settings" / "index.html",
            ROOT / "pages" / "a_manage" / "semantic" / "index.html",
        ]

        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertIn("data-nav-page", source, str(path))
            self.assertNotIn("../", source, str(path))
            self.assertIn('target="_top"', source, str(path))

        manage_html = (ROOT / "pages" / "a_manage" / "index.html").read_text(
            encoding="utf-8"
        )
        for page_name in ("catalog", "settings", "semantic"):
            self.assertIn(
                f'href="/#/plugin-page/meme_manager_master/{page_name}"',
                manage_html,
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

    def test_pack_switch_refreshes_dashboard_navigation_params(self):
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

    def test_capture_index_links_use_named_dashboard_targets(self):
        html = (ROOT / "pages" / "a_manage" / "semantic" / "index.html").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "pages" / "a_manage" / "semantic" / "script.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('data-nav-page="a_manage"', html)
        self.assertNotIn("../", html)
        self.assertIn('target="_top"', html)
        self.assertIn("plugin-page/meme_manager_master", script)
        self.assertNotIn("asset_token", script)

    def test_settings_assets_have_cache_busters_in_both_page_copies(self):
        for path in (
            ROOT / "pages" / "settings" / "index.html",
            ROOT / "pages" / "a_manage" / "settings" / "index.html",
        ):
            source = path.read_text(encoding="utf-8")
            self.assertRegex(source, r'./style\.css\?v=[^" ]+', str(path))
            self.assertRegex(source, r'./script\.js\?v=[^" ]+', str(path))


if __name__ == "__main__":
    unittest.main()
