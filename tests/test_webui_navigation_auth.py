import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
A_MANAGE = ROOT / "pages" / "a_manage"
REMAINING_PAGE_DIRS = ("semantic",)
ASSET_VERSION = "20260818-workspace-layout-1"


class WebUINavigationAuthTests(unittest.TestCase):
    def test_pages_do_not_manually_forward_asset_tokens(self):
        sources = [
            A_MANAGE / page_name / "script.js" for page_name in REMAINING_PAGE_DIRS
        ]

        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("asset_token", source, str(path))

    def test_remaining_page_links_use_in_frame_relative_paths(self):
        sources = [
            A_MANAGE / page_name / "index.html" for page_name in REMAINING_PAGE_DIRS
        ]

        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("data-nav-page", source, str(path))
            self.assertNotIn('target="_top"', source, str(path))
            self.assertNotIn('href="/#/plugin-page/', source, str(path))
            self.assertNotIn('data-nav-page="a_manage"', source, str(path))
            self.assertNotIn('href="../index.html"', source, str(path))

    def test_nested_page_assets_are_copied_into_the_a_manage_scope(self):
        for page_name in REMAINING_PAGE_DIRS:
            page_root = A_MANAGE / page_name
            self.assertTrue((page_root / "index.html").is_file(), page_name)
            self.assertTrue((page_root / "script.js").is_file(), page_name)
            self.assertTrue((page_root / "style.css").is_file(), page_name)

    def test_settings_and_catalog_pages_are_removed(self):
        for page_name in ("settings", "catalog"):
            self.assertFalse(
                (A_MANAGE / page_name / "index.html").is_file(),
                f"{page_name} page must be removed",
            )

    def test_entry_redirect_does_not_copy_static_asset_token(self):
        source = (ROOT / "pages" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("asset_token", source)
        self.assertIn("plugin-page/meme_manager_master/a_manage", source)
        self.assertNotIn("a_manage/semantic", source)
        self.assertNotIn('"a_manage"', source)

    def test_a_manage_entry_redirects_to_semantic_workspace(self):
        source = (A_MANAGE / "index.html").read_text(encoding="utf-8")
        self.assertIn("./semantic/index.html", source)
        self.assertNotIn("emoji-categories", source)
        self.assertNotIn("MemeManagerUI", source)
        self.assertNotIn("data-nav-page", source)

    def test_capture_index_page_has_no_cross_page_links(self):
        html = (A_MANAGE / "semantic" / "index.html").read_text(encoding="utf-8")
        script = (A_MANAGE / "semantic" / "script.js").read_text(encoding="utf-8")

        self.assertNotIn("设置中心", html)
        self.assertNotIn("资源广场", html)
        self.assertNotIn("settings/index.html", html)
        self.assertNotIn("catalog/index.html", html)
        self.assertNotIn('data-nav-page="settings"', html)
        self.assertNotIn('data-nav-page="catalog"', html)
        self.assertNotIn("allowedPages", script)
        self.assertNotIn("applySecureNavLinks", script)
        self.assertNotIn('target="_top"', html)
        self.assertNotIn("asset_token", script)

    def test_remaining_navigation_scripts_have_fresh_cache_busters(self):
        pages = {
            A_MANAGE / "semantic" / "index.html": "script.js",
        }

        for path, script_name in pages.items():
            source = path.read_text(encoding="utf-8")
            self.assertIn(
                f"{script_name}?v={ASSET_VERSION}",
                source,
                str(path),
            )


if __name__ == "__main__":
    unittest.main()
