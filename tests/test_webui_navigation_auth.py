import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class WebUINavigationAuthTests(unittest.TestCase):
    def test_entry_redirect_keeps_static_asset_token(self):
        source = (ROOT / "pages" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('if (key === "asset_token")', source)

    def test_navigation_helpers_forward_static_asset_token(self):
        sources = [
            ROOT / "pages" / "a_manage" / "api.js",
            ROOT / "pages" / "catalog" / "script.js",
            ROOT / "pages" / "settings" / "script.js",
        ]

        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertIn('"asset_token"', source, str(path))

    def test_capture_index_links_are_auth_aware(self):
        html = (ROOT / "pages" / "semantic" / "index.html").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "pages" / "semantic" / "script.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("data-nav-target", html)
        self.assertIn('"asset_token"', script)


if __name__ == "__main__":
    unittest.main()
