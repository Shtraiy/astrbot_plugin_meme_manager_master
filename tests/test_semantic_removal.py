from pathlib import Path
import tempfile
import unittest

from backend.semantic_cleanup import cleanup_legacy_semantic_data
from mixins.web_routes import enabled_route_specs

ROOT = Path(__file__).resolve().parents[1]


class SemanticRemovalTests(unittest.TestCase):
    def test_cleanup_removes_only_legacy_semantic_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pack = root / "packs" / "demo"
            (pack / "memes").mkdir(parents=True)
            (pack / "memes" / "cat.png").write_bytes(b"image")
            (pack / "semantic_metadata.json").write_text("{}", encoding="utf-8")
            (root / "semantic_indexes" / "demo").mkdir(parents=True)
            (root / "selection_rules.json").write_text("{}", encoding="utf-8")

            removed = cleanup_legacy_semantic_data(root)

            self.assertGreaterEqual(removed, 2)
            self.assertFalse((pack / "semantic_metadata.json").exists())
            self.assertFalse((root / "semantic_indexes").exists())
            self.assertTrue((pack / "memes" / "cat.png").exists())
            self.assertTrue((root / "selection_rules.json").exists())

    def test_runtime_no_longer_constructs_semantic_tasks(self):
        source = (ROOT / "manager_base.py").read_text(encoding="utf-8")
        self.assertNotIn("SemanticTaskManager", source)
        self.assertNotIn("VectorSemanticService", source)

    def test_semantic_routes_are_not_registered(self):
        paths = {spec.path for spec in enabled_route_specs({"core", "catalog_index"})}
        self.assertFalse(
            any(path == "meme_image_semantic" or path.startswith("semantic/") for path in paths)
        )

    def test_manage_page_has_no_semantic_controls(self):
        html = (ROOT / "pages" / "a_manage" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("../semantic/index.html", html)
        self.assertNotIn("pack-semantic-status", html)
        self.assertNotIn("rebuild-pack-vectors-btn", html)
        self.assertIn("Image semanticization controls were removed", html)

    def test_manage_scripts_do_not_call_semantic_endpoints(self):
        paths = ("emoji.js", "pack.js", "script.js")
        source = "\n".join(
            (ROOT / "pages" / "a_manage" / path).read_text(encoding="utf-8")
            for path in paths
        )
        self.assertNotIn("semantic/", source)


if __name__ == "__main__":
    unittest.main()
