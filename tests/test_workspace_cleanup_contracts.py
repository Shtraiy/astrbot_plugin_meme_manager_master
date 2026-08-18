import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _definition_count(relative: str, name: str) -> int:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in tree.body
    )


class WorkspaceCleanupContractTests(unittest.TestCase):
    def test_retired_backup_facade_is_not_exported(self):
        application = (ROOT / "application" / "__init__.py").read_text(encoding="utf-8")
        services = (ROOT / "application" / "services.py").read_text(encoding="utf-8")
        manager = (ROOT / "manager_base.py").read_text(encoding="utf-8")
        self.assertNotIn("PackBackupService", application)
        self.assertNotIn("PackBackupService", services)
        self.assertNotIn("PackBackupService", manager)

    def test_retired_backup_module_is_removed(self):
        self.assertFalse((ROOT / "backend" / "pack_backup.py").exists())

    def test_storage_policy_exports_are_not_redeclared(self):
        for name in ("is_safe_category_segment", "resolve_safe_category_dir", "_safe_extension"):
            self.assertEqual(_definition_count("storage.py", name), 1, name)


if __name__ == "__main__":
    unittest.main()
