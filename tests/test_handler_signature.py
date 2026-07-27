import ast
import unittest
from pathlib import Path


class HandlerSignatureTests(unittest.TestCase):
    def test_on_message_accepts_pipeline_extra_arguments(self):
        source = Path(__file__).resolve().parents[1] / "main.py"
        module = ast.parse(source.read_text(encoding="utf-8"))
        handler = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_message"
        )

        self.assertIsNotNone(handler.args.vararg)
        self.assertIsNotNone(handler.args.kwarg)

    def test_library_batch_failure_returns_instead_of_spamming_remaining_batches(self):
        source = Path(__file__).resolve().parents[1] / "main.py"
        module = ast.parse(source.read_text(encoding="utf-8"))
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
            any(any(isinstance(node, ast.Return) for node in handler.body) for handler in handlers)
        )


if __name__ == "__main__":
    unittest.main()
