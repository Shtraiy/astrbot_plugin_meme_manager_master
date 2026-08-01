from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from pathlib import Path

from capture_activity import load_capture_activity, record_capture_event


class CaptureActivityConcurrencyTests(unittest.TestCase):
    def test_parallel_events_are_not_lost(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir)

            def write(index: int) -> None:
                record_capture_event(
                    pack_dir,
                    category="happy",
                    filename=f"{index}.png",
                    digest=f"digest-{index}",
                    status="pending",
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(write, range(100)))
            events = load_capture_activity(pack_dir)["events"]
            self.assertEqual(len(events), 100)
            self.assertEqual({item["sha256"] for item in events}, {f"digest-{i}" for i in range(100)})


if __name__ == "__main__":
    unittest.main()
