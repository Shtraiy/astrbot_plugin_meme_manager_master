import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_is_v221_and_mentions_removed_manage_page(self):
        metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("version: v2.2.1", metadata)
        self.assertIn("version-v2.2.1", readme)
        self.assertIn("## [v2.2.1] - 2026-08-17", changelog)
        self.assertIn("恢复 AstrBot 插件页面入口", changelog)
        self.assertIn("入口即表情索引", readme)
        self.assertNotIn("## [Unreleased]", changelog)

    def test_runtime_registration_version_matches_manifest(self):
        metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
        manifest_version = next(
            line.split(":", 1)[1].strip()
            for line in metadata.splitlines()
            if line.startswith("version:")
        )

        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        registration_version = None
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "register"
                    and len(decorator.args) >= 4
                ):
                    continue
                registration_version = ast.literal_eval(decorator.args[3])
                break
            if registration_version is not None:
                break

        self.assertEqual(registration_version, manifest_version.removeprefix("v"))


if __name__ == "__main__":
    unittest.main()
