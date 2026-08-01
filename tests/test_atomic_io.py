import json
import tempfile
import unittest
from pathlib import Path

from backend.atomic_io import atomic_write_bytes, atomic_write_json


class AtomicIoTests(unittest.TestCase):
    def test_atomic_write_bytes_creates_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data.bin"
            atomic_write_bytes(path, b"hello")
            self.assertEqual(path.read_bytes(), b"hello")
            self.assertEqual(list(path.parent.glob(".data.bin.*.tmp")), [])

    def test_atomic_write_json_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            path.write_text('{"version": 1}\n', encoding="utf-8")
            atomic_write_json(path, {"version": 2, "name": "表情包"})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"version": 2, "name": "表情包"},
            )

    def test_failed_json_serialization_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            path.write_text('{"version": 1}', encoding="utf-8")
            with self.assertRaises(TypeError):
                atomic_write_json(path, {"bad": object()})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 1})
            self.assertEqual(list(path.parent.glob(".state.json.*.tmp")), [])

    def test_successful_write_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "state.json"
            atomic_write_json(path, {"a": 1})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1})
            self.assertEqual(list(path.parent.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
