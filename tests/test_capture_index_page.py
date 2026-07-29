import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CaptureIndexPageTests(unittest.TestCase):
    def test_page_no_longer_exposes_full_semantic_task_controls(self):
        html = (ROOT / "pages" / "semantic" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "pages" / "semantic" / "script.js").read_text(encoding="utf-8")
        self.assertIn("表情索引", html)
        self.assertNotIn("一键完整语义化", html)
        self.assertNotIn('data-action="start"', html)
        self.assertNotIn('apiGet("semantic/status"', script)
        self.assertNotIn('apiGet("semantic/items"', script)
        self.assertIn('apiGet("semantic/capture-workspace"', script)


if __name__ == "__main__":
    unittest.main()
