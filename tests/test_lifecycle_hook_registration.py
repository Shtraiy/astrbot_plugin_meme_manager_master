import ast
import copy
import unittest
from pathlib import Path


class _RecordingFilter:
    def __init__(self):
        self.handlers = []

    def on_astrbot_loaded(self):
        def decorator(handler):
            self.handlers.append(handler)
            return handler

        return decorator


def _registered_startup_handlers(path: Path, module_name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        methods = []
        for statement in node.body:
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            startup_decorators = [
                decorator
                for decorator in statement.decorator_list
                if isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "on_astrbot_loaded"
            ]
            if not startup_decorators:
                continue
            method = copy.deepcopy(statement)
            method.body = [ast.Pass()]
            method.decorator_list = startup_decorators
            methods.append(method)
        if methods:
            classes.append(
                ast.ClassDef(
                    name=node.name,
                    bases=[],
                    keywords=[],
                    body=methods,
                    decorator_list=[],
                )
            )

    recording_filter = _RecordingFilter()
    namespace = {"__name__": module_name, "filter": recording_filter}
    registration_module = ast.fix_missing_locations(
        ast.Module(body=classes, type_ignores=[])
    )
    exec(compile(registration_module, str(path), "exec"), namespace)
    return recording_filter.handlers


class LifecycleHookRegistrationTests(unittest.TestCase):
    def test_plugin_registers_no_astrbot_loaded_handlers(self):
        root = Path(__file__).parents[1]
        handlers = []
        handlers.extend(
            _registered_startup_handlers(
                root / "manager_base.py",
                "meme_manager_master.manager_base",
            )
        )
        handlers.extend(
            _registered_startup_handlers(
                root / "main.py",
                "meme_manager_master.main",
            )
        )

        self.assertEqual(handlers, [])


if __name__ == "__main__":
    unittest.main()
