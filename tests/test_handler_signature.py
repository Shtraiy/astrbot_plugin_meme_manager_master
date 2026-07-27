import ast
import unittest
from pathlib import Path


class HandlerSignatureTests(unittest.TestCase):
    def _module(self):
        source = Path(__file__).resolve().parents[1] / "main.py"
        return ast.parse(source.read_text(encoding="utf-8"))

    def test_on_message_accepts_pipeline_extra_arguments(self):
        module = self._module()
        handler = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_message"
        )

        self.assertIsNotNone(handler.args.vararg)
        self.assertIsNotNone(handler.args.kwarg)

    def test_library_batch_failure_returns_instead_of_spamming_remaining_batches(self):
        module = self._module()
        ensure = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_ensure_library_index"
        )

        handlers = [
            node
            for node in ast.walk(ensure)
            if isinstance(node, ast.ExceptHandler)
        ]
        self.assertTrue(
            any(
                any(isinstance(node, ast.Return) for node in ast.walk(handler))
                for handler in handlers
            )
        )

    def test_library_batch_failure_has_single_image_fallback(self):
        module = self._module()
        ensure = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_ensure_library_index"
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_describe_library_single"
                for node in ast.walk(ensure)
            )
        )

    def test_vision_failures_are_explicitly_excluded_before_save(self):
        module = self._module()
        recognize = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_recognize_image"
        )
        process = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_process_batch"
        )

        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "vision_failure_result"
                for node in ast.walk(recognize)
            )
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Constant)
                and node.value == "vision_error"
                for node in ast.walk(process)
            )
        )

    def test_frontend_save_and_index_commit_share_storage_lock(self):
        module = self._module()
        process = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_process_batch"
        )
        index = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_ensure_library_index"
        )

        def uses_save_lock(node):
            return any(
                isinstance(item, ast.AsyncWith)
                and any(
                    isinstance(context.context_expr, ast.Attribute)
                    and context.context_expr.attr == "_save_lock"
                    for context in item.items
                )
                for item in ast.walk(node)
            )

        self.assertTrue(uses_save_lock(process))
        self.assertTrue(uses_save_lock(index))


if __name__ == "__main__":
    unittest.main()
