import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "a_manage"


class WebUINavigationAuthTests(unittest.TestCase):
    def test_loaded_page_scripts_do_not_read_or_forward_asset_tokens(self):
        html = (PAGE / "index.html").read_text(encoding="utf-8")
        scripts = [
            PAGE / "api.js",
            PAGE / "pack.js",
            PAGE / "script.js",
            PAGE / "capture-index.js",
            PAGE / "settings.js",
            PAGE / "router.js",
        ]

        self.assertNotIn("asset_token", html)
        for path in scripts:
            self.assertNotIn("asset_token", path.read_text(encoding="utf-8"), str(path))

    def test_navigation_uses_hashes_in_the_single_document(self):
        html = (PAGE / "index.html").read_text(encoding="utf-8")
        router = (PAGE / "router.js").read_text(encoding="utf-8")

        for route in ("manage", "index", "settings"):
            self.assertIn(f'href="#{route}"', html)
        self.assertIn('window.addEventListener("hashchange"', router)
        self.assertIn("window.history.replaceState", router)
        self.assertNotIn("location.href =", router)
        self.assertNotIn("/index.html", router)

    def test_pack_switch_updates_shared_query_without_rewriting_navigation_links(self):
        pack = (PAGE / "pack.js").read_text(encoding="utf-8")
        router = (PAGE / "router.js").read_text(encoding="utf-8")

        self.assertIn("router?.updateManagedPackQuery", pack)
        self.assertIn('nextUrl.searchParams.set("managed_pack_id"', router)
        self.assertNotIn("applySecureNavLinks", pack)

    def test_single_shell_loads_every_view_asset_with_cache_busters(self):
        html = (PAGE / "index.html").read_text(encoding="utf-8")
        for asset in (
            "style.css",
            "capture-index.css",
            "settings.css",
            "api.js",
            "script.js",
            "capture-index.js",
            "settings.js",
            "router.js",
        ):
            escaped_asset = asset.replace(".", r"\.")
            self.assertRegex(html, rf'{escaped_asset}\?v=[^" ]+')

    def test_entry_redirect_does_not_copy_static_asset_token(self):
        source = (ROOT / "pages" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("asset_token", source)
        self.assertIn("plugin-page/meme_manager_master/a_manage", source)


if __name__ == "__main__":
    unittest.main()
