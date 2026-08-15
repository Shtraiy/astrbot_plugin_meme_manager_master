import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_is_v215_and_mentions_primary_semantic_index(self):
        metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("version: v2.1.5", metadata)
        self.assertIn("version-v2.1.5", readme)
        self.assertIn("## [v2.1.5] - 2026-08-15", changelog)
        self.assertIn("主分类", changelog)
        self.assertIn("图片文字", changelog)


if __name__ == "__main__":
    unittest.main()
