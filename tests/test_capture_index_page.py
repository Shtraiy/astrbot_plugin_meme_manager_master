import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CaptureIndexPageTests(unittest.TestCase):
    def test_semantic_page_and_assets_are_removed(self):
        self.assertFalse((ROOT / "pages" / "semantic").exists())


if __name__ == "__main__":
    unittest.main()
