import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class WebUINavigationAuthTests(unittest.TestCase):
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

        self.assertNotIn(
            "plugin-page/meme_manager_master",
            (ROOT / "pages" / "a_manage" / "api.js").read_text(encoding="utf-8"),
        )

    def test_page_links_stay_inside_the_a_manage_page_scope(self):
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

        manage_html = (ROOT / "pages" / "a_manage" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('href="./catalog/index.html"', manage_html)
        self.assertIn('href="./settings/index.html"', manage_html)
        self.assertIn('href="./semantic/index.html"', manage_html)

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
        self.assertIn("../", html)
        self.assertNotIn('target = "_top"', script)
        self.assertNotIn("asset_token", script)


if __name__ == "__main__":
    unittest.main()
