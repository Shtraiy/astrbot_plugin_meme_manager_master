import unittest
from pathlib import Path


class CaptureClassReferenceTests(unittest.TestCase):
    def test_capture_module_has_no_stale_meme_stealer_reference(self):
        source = (Path(__file__).parents[1] / "capture.py").read_text(encoding="utf-8")
        self.assertNotIn("MemeStealer", source)


if __name__ == "__main__":
    unittest.main()
