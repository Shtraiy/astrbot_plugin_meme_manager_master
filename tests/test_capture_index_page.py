import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CaptureIndexPageTests(unittest.TestCase):
    def test_capture_index_page_is_available(self):
        page = ROOT / "pages" / "semantic" / "index.html"
        self.assertTrue(page.is_file())
        source = page.read_text(encoding="utf-8")
        self.assertIn("表情索引", source)
        self.assertIn("capture-indexed-items", source)
        self.assertIn("capture-pending-items", source)
        self.assertIn("capture-reindex-button", source)
        self.assertIn("capture-category-filters", source)
        self.assertIn("sections-stack", source)

    def test_nested_capture_index_page_has_the_same_vertical_workspace_contract(self):
        page = ROOT / "pages" / "a_manage" / "semantic" / "index.html"
        source = page.read_text(encoding="utf-8")
        script = page.with_name("script.js").read_text(encoding="utf-8")
        style = page.with_name("style.css").read_text(encoding="utf-8")
        self.assertIn("capture-reindex-button", source)
        self.assertIn("capture-category-filters", source)
        self.assertIn("sections-stack", source)
        self.assertIn('size: "preview"', script)
        self.assertIn('apiPost("capture/reindex"', script)
        self.assertIn(".sections-stack", style)

    def test_reindex_button_is_not_silently_disabled_by_model_index_state(self):
        for script_path in (
            ROOT / "pages" / "semantic" / "script.js",
            ROOT / "pages" / "a_manage" / "semantic" / "script.js",
        ):
            script = script_path.read_text(encoding="utf-8")
            self.assertNotIn(
                'reindexButton.disabled = state.status === "running";',
                script,
            )
            self.assertIn("正在重索引表情文件", script)

    def test_reindex_progress_contract_exists_in_both_page_copies(self):
        for page_dir in (ROOT / "pages" / "semantic", ROOT / "pages" / "a_manage" / "semantic"):
            source = (page_dir / "index.html").read_text(encoding="utf-8")
            script = (page_dir / "script.js").read_text(encoding="utf-8")
            style = (page_dir / "style.css").read_text(encoding="utf-8")
            self.assertIn("capture-reindex-progress", source)
            self.assertIn("capture-reindex-progress-bar", source)
            self.assertIn('apiGet("capture/reindex/status"', script)
            self.assertIn("setTimeout", script)
            self.assertIn("reindex-progress", style)

    def test_capture_index_page_uses_non_semantic_capture_routes(self):
        source = (ROOT / "pages" / "semantic" / "script.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('"capture/workspace"', source)
        self.assertIn('"capture/index"', source)
        self.assertNotIn('"semantic/capture-workspace"', source)
        self.assertNotIn('"semantic/capture-index"', source)


if __name__ == "__main__":
    unittest.main()
