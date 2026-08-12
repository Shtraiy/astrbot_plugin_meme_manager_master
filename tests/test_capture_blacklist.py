import json
import tempfile
import threading
import unittest
from pathlib import Path

from capture_blacklist import CaptureBlacklist


class CaptureBlacklistTests(unittest.TestCase):
    def test_missing_file_is_empty_and_add_persists_sorted_unique_digests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            blacklist = CaptureBlacklist(root)
            first = "b" * 64
            second = "a" * 64

            self.assertFalse(blacklist.contains(first))
            self.assertEqual(blacklist.add({first, second, first}), 2)
            self.assertEqual(blacklist.add({first}), 0)

            saved = json.loads((root / "capture_blacklist.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, {"schema_version": 1, "sha256s": [second, first]})
            self.assertTrue(CaptureBlacklist(root).contains(second))

    def test_invalid_digest_is_rejected_without_creating_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            blacklist = CaptureBlacklist(root)

            with self.assertRaisesRegex(ValueError, "SHA-256"):
                blacklist.add({"not-a-digest"})

            self.assertFalse((root / "capture_blacklist.json").exists())

    def test_corrupt_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "capture_blacklist.json"
            path.write_text("{not json", encoding="utf-8")
            blacklist = CaptureBlacklist(root)

            with self.assertRaisesRegex(ValueError, "黑名单文件损坏"):
                blacklist.contains("a" * 64)
            with self.assertRaisesRegex(ValueError, "黑名单文件损坏"):
                blacklist.run_if_allowed("a" * 64, lambda: "saved")

    def test_concurrent_additions_do_not_lose_digests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            blacklist = CaptureBlacklist(root)
            digests = [f"{index:064x}" for index in range(20)]
            threads = [threading.Thread(target=blacklist.add, args=({digest},)) for digest in digests]

            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(blacklist.load(), set(digests))

    def test_run_if_allowed_serializes_check_with_operation(self):
        with tempfile.TemporaryDirectory() as temporary:
            blacklist = CaptureBlacklist(Path(temporary))
            digest = "c" * 64
            operation_started = threading.Event()
            release_operation = threading.Event()
            results = []

            def operation():
                operation_started.set()
                release_operation.wait(timeout=2)
                return "saved"

            runner = threading.Thread(
                target=lambda: results.append(blacklist.run_if_allowed(digest, operation))
            )
            runner.start()
            self.assertTrue(operation_started.wait(timeout=2))
            adder = threading.Thread(target=blacklist.add, args=({digest},))
            adder.start()
            self.assertTrue(adder.is_alive())
            release_operation.set()
            runner.join(timeout=2)
            adder.join(timeout=2)

            self.assertEqual(results, [(True, "saved")])
            self.assertTrue(blacklist.contains(digest))


if __name__ == "__main__":
    unittest.main()
