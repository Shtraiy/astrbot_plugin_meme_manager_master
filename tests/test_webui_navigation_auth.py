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
            self.assertIn("plugin-page/meme_manager_master", source, str(path))

    def test_page_links_use_named_targets_instead_of_parent_paths(self):
        sources = [
            ROOT / "pages" / "a_manage" / "index.html",
            ROOT / "pages" / "catalog" / "index.html",
            ROOT / "pages" / "settings" / "index.html",
            ROOT / "pages" / "semantic" / "index.html",
        ]

        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("../", source, str(path))
            self.assertIn("data-nav-page", source, str(path))

    def test_entry_redirect_does_not_copy_static_asset_token(self):
        source = (ROOT / "pages" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("asset_token", source)
        self.assertIn("plugin-page/meme_manager_master/a_manage", source)

    def test_capture_index_links_use_named_dashboard_targets(self):
        html = (ROOT / "pages" / "semantic" / "index.html").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "pages" / "semantic" / "script.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('data-nav-page="a_manage"', html)
        self.assertNotIn("../", html)
        self.assertIn("plugin-page/meme_manager_master", script)
        self.assertNotIn("asset_token", script)


if __name__ == "__main__":
    unittest.main()
