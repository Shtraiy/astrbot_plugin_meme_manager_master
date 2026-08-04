import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _imports(relative: str) -> set[str]:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    return modules


class CoreImportBoundaryTests(unittest.TestCase):
    def test_pack_resolver_uses_domain_mapping_not_semantic_runtime_module(self):
        imports = _imports("backend/pack_resolver.py")
        self.assertNotIn(".semantic_models", imports)
        self.assertIn("domain.category_mapping", imports)

    def test_manager_base_does_not_import_semantic_runtime_module(self):
        imports = _imports("manager_base.py")
        self.assertNotIn(".backend.semantic_models", imports)
        self.assertIn("domain.category_mapping", imports)

    def test_event_handlers_import_only_lazy_semantic_compatibility(self):
        imports = _imports("mixins/event_handlers.py")
        self.assertNotIn("backend.semantic_models", imports)
        self.assertNotIn("backend.semantic_query", imports)
        self.assertNotIn("backend.semantic_storage", imports)
        self.assertIn("backend.semantic_compat", imports)

    def test_pack_and_category_adapters_use_lazy_semantic_compatibility(self):
        for relative in (
            "backend/category_manager.py",
            "backend/pack_repository.py",
            "backend/pack_storage.py",
        ):
            imports = _imports(relative)
            self.assertFalse(any(module.startswith("backend.semantic_") for module in imports), relative)
            self.assertIn("semantic_compat", " ".join(imports), relative)

    def test_config_uses_legacy_cleanup_adapter_without_semantic_module_import(self):
        imports = _imports("config.py")
        self.assertNotIn("backend.semantic_cleanup", imports)
        self.assertIn("infrastructure.legacy_cleanup", imports)

    def test_domain_modules_do_not_import_framework_or_filesystem_adapters(self):
        for path in (ROOT / "domain").glob("*.py"):
            imports = _imports(str(path.relative_to(ROOT)))
            forbidden = {
                module
                for module in imports
                if module.startswith(("astrbot", "quart", "PIL", "requests"))
                or module in {"json", "os", "shutil", "aiohttp"}
            }
            self.assertEqual(forbidden, set(), path.name)


if __name__ == "__main__":
    unittest.main()
