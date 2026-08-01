import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _parse(relative: str) -> ast.Module:
    return ast.parse((ROOT / relative).read_text(encoding="utf-8"))


class WebApiModuleBoundaryTests(unittest.TestCase):
    def test_api_mixins_do_not_import_shutil(self):
        for relative in (
            "mixins/emoji_api.py",
            "mixins/pack_api.py",
            "mixins/semantic_api.py",
        ):
            tree = _parse(relative)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.extend(alias.name for alias in node.names)
            self.assertNotIn("shutil", imports, relative)

    def test_api_mixins_do_not_import_requests(self):
        for relative in (
            "mixins/emoji_api.py",
            "mixins/pack_api.py",
            "mixins/semantic_api.py",
        ):
            tree = _parse(relative)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.extend(alias.name for alias in node.names)
            self.assertNotIn("requests", imports, relative)

    def test_api_mixins_never_call_os_remove(self):
        for relative in (
            "mixins/emoji_api.py",
            "mixins/pack_api.py",
            "mixins/semantic_api.py",
        ):
            tree = _parse(relative)
            calls = []
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "remove"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                ):
                    calls.append(node.lineno)
            self.assertEqual(calls, [], relative)


class CaptureBoundaryTests(unittest.TestCase):
    def test_capture_pipeline_registers_no_astrbot_filter(self):
        tree = _parse("capture_pipeline.py")
        filter_import = any(
            isinstance(node, ast.ImportFrom)
            and (node.module or "").endswith("event.filter")
            for node in ast.walk(tree)
        )
        self.assertFalse(filter_import)
        decorators = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for node in node.decorator_list
        ]
        self.assertEqual(decorators, [])

    def test_meme_selection_does_not_import_webui_request_or_jsonify(self):
        tree = _parse("meme_selection.py")
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module.startswith("quart") or module.startswith("flask"):
                self.fail(f"meme_selection.py imports WebUI module {module}")
            for alias in node.names:
                self.assertNotEqual(alias.name, "jsonify")
                self.assertNotEqual(alias.name, "request")

    def test_capture_pipeline_has_no_file_write_primitives(self):
        tree = _parse("capture_pipeline.py")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "replace",
                "rmtree",
                "dump",
            }:
                value_id = (
                    node.func.value.id
                    if isinstance(node.func.value, ast.Name)
                    else ""
                )
                if value_id in {"os", "shutil", "json"}:
                    self.fail(f"capture_pipeline.py calls {value_id}.{node.func.attr}")

    def test_capture_py_has_no_direct_json_dump_replace_or_rmtree(self):
        tree = _parse("capture.py")
        banned: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            value_id = (
                node.func.value.id
                if isinstance(node.func.value, ast.Name)
                else ""
            )
            if value_id == "json" and node.func.attr == "dump":
                banned.append(f"json.dump at {node.lineno}")
            if value_id == "os" and node.func.attr == "replace":
                banned.append(f"os.replace at {node.lineno}")
            if value_id == "shutil" and node.func.attr == "rmtree":
                banned.append(f"shutil.rmtree at {node.lineno}")
        self.assertEqual(banned, [])


class ManagerInitStructureTests(unittest.TestCase):
    def test_manager_init_initializes_runtime_state(self):
        tree = _parse("manager_base.py")
        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MemeSender"
        )
        init = next(
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        init_source = ast.get_source_segment(
            (ROOT / "manager_base.py").read_text(encoding="utf-8"),
            init,
        )
        for statement in (
            "self.upload_states = {}",
            "self.pending_images = {}",
            "self.category_manager = CategoryManager()",
            "self._register_web_apis()",
        ):
            self.assertIn(statement, init_source, statement)

    def test_vector_manager_factory_is_class_level_not_nested(self):
        tree = _parse("manager_base.py")
        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MemeSender"
        )
        init = next(
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        factory = next(
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_create_vector_semantic_manager"
        )
        self.assertGreater(factory.lineno, init.end_lineno)


if __name__ == "__main__":
    unittest.main()
