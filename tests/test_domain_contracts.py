import tempfile
import unittest
from pathlib import Path

from domain.models import (
    Category,
    MemeId,
    OperationError,
    PackContext,
    PackId,
    SelectionResult,
)
from infrastructure.path_boundary import PathBoundary


class DomainContractTests(unittest.TestCase):
    def test_pack_id_accepts_safe_identifiers_and_rejects_paths(self):
        self.assertEqual(str(PackId("builtin-default")), "builtin-default")
        for value in ("", ".", "..", "../escape", "C:/escape", "a/b", "a\\b"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    PackId(value)

    def test_domain_values_are_normalized_and_immutable(self):
        category = Category("  angry ")
        meme_id = MemeId("  image-1  ")
        result = SelectionResult(selected_id=meme_id, category=category, confidence=1.2)
        self.assertEqual(category.value, "angry")
        self.assertEqual(meme_id.value, "image-1")
        self.assertEqual(result.confidence, 1.0)
        with self.assertRaises((AttributeError, TypeError)):
            result.selected_id = MemeId("other")

    def test_pack_context_resolves_only_inside_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = PackContext(PackId("demo"), root / "demo", root)
            self.assertEqual(context.resolve("memes"), (root / "demo" / "memes").resolve())
            with self.assertRaises(ValueError):
                context.resolve("../outside")

    def test_path_boundary_rejects_root_and_parent_escape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            boundary = PathBoundary(root)
            self.assertEqual(boundary.child("nested", "file.json"), (root / "nested" / "file.json").resolve())
            for parts in ((), ("..",), ("nested", "..", "..", "outside")):
                with self.subTest(parts=parts):
                    with self.assertRaises(ValueError):
                        boundary.child(*parts)

    def test_operation_error_keeps_machine_readable_code(self):
        error = OperationError("invalid_pack", "pack id is invalid")
        self.assertEqual(error.code, "invalid_pack")
        self.assertEqual(str(error), "pack id is invalid")


if __name__ == "__main__":
    unittest.main()
