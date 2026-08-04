import tempfile
import unittest
from pathlib import Path

from domain.models import PackContext
from infrastructure.pack_resolver import FilesystemPackResolver


class FilesystemPackResolverTests(unittest.TestCase):
    def test_resolve_returns_bounded_pack_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "demo").mkdir()
            resolver = FilesystemPackResolver(root)
            context = resolver.resolve("demo")
            self.assertIsInstance(context, PackContext)
            self.assertEqual(context.root, (root / "demo").resolve())

    def test_resolve_rejects_missing_pack_when_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            resolver = FilesystemPackResolver(temp_dir, require_exists=True)
            with self.assertRaises(FileNotFoundError):
                resolver.resolve("missing")


if __name__ == "__main__":
    unittest.main()
