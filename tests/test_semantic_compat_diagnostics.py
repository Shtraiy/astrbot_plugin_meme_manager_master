import asyncio
import unittest
from unittest.mock import patch

from backend import semantic_compat


class SemanticCompatDiagnosticTests(unittest.TestCase):
    def test_search_reports_unavailable_dependency_without_startup_import(self):
        with patch.object(
            semantic_compat,
            "_semantic_query",
            side_effect=ModuleNotFoundError("semantic provider missing"),
        ):
            result = asyncio.run(semantic_compat.search_memes("hello"))

        self.assertEqual(result["candidates"], [])
        self.assertIn("unavailable", result["reason"])
        self.assertIn("semantic provider missing", result["reason"])

    def test_search_reports_provider_runtime_failure_instead_of_unavailable(self):
        class Query:
            async def search_memes(self, *_args, **_kwargs):
                raise RuntimeError("provider timed out")

        with patch.object(semantic_compat, "_semantic_query", return_value=Query()):
            result = asyncio.run(semantic_compat.search_memes("hello"))

        self.assertEqual(result["candidates"], [])
        self.assertIn("runtime failure", result["reason"])
        self.assertIn("provider timed out", result["reason"])
