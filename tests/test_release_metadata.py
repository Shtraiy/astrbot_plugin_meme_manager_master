import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_is_v217_and_mentions_resumable_full_semantic_reindex(self):
        metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("version: v2.1.7", metadata)
        self.assertIn("version-v2.1.7", readme)
        self.assertIn("## [v2.1.7] - 2026-08-15", changelog)
        self.assertIn("全量语义重索引", changelog)
        self.assertIn("完整 v4", changelog)
        self.assertIn("full_reindex_status", changelog)
        self.assertIn("检查点", changelog)


if __name__ == "__main__":
    unittest.main()
