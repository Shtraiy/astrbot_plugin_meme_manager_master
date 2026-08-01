import unittest

from backend.pack_protocol import (
    validate_pack_manifest,
    validate_source_descriptor,
    validate_transfer_manifest,
)


class PackProtocolTests(unittest.TestCase):
    def test_transfer_manifest_normalizes_features(self):
        result = validate_transfer_manifest(
            {
                "format": "astrbot-meme-pack",
                "format_version": "2",
                "export_mode": "share",
                "features": {"semantic_metadata": 1},
            }
        )
        self.assertEqual(result["format_version"], 2)
        self.assertEqual(
            result["features"], {"semantic_metadata": True, "vectors": False}
        )

    def test_source_descriptor_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            validate_source_descriptor(
                {"type": "github", "repo": "owner/repo", "ref": "main", "subpath": "../pack"}
            )

    def test_source_descriptor_rejects_unsafe_repo_and_ref(self):
        invalid_sources = [
            {"type": "github", "repo": "https://github.com/owner/repo", "ref": "main", "subpath": "pack"},
            {"type": "github", "repo": "owner/repo/extra", "ref": "main", "subpath": "pack"},
            {"type": "github", "repo": "owner/repo", "ref": "../main", "subpath": "pack"},
            {"type": "github", "repo": "owner/repo", "ref": "main\nX", "subpath": "pack"},
            {"type": "github", "repo": "owner/repo", "ref": "main", "subpath": "./pack"},
        ]
        for source in invalid_sources:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    validate_source_descriptor(source)

    def test_pack_manifest_normalizes_category_descriptions(self):
        result = validate_pack_manifest(
            {
                "id": "cats",
                "name": "Cats",
                "version": "1.0.0",
                "categories": {"happy": {}, "sad": "伤心场景"},
            }
        )
        self.assertEqual(result["categories"]["happy"]["description"], "请添加描述")
        self.assertEqual(result["categories"]["sad"]["description"], "伤心场景")

    def test_pack_manifest_rejects_unsafe_category_names(self):
        with self.assertRaises(ValueError):
            validate_pack_manifest(
                {
                    "id": "cats",
                    "name": "Cats",
                    "version": "1.0.0",
                    "categories": {"../outside": {"description": "bad"}},
                }
            )


if __name__ == "__main__":
    unittest.main()
