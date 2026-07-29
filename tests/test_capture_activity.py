import json
import tempfile
import unittest
from pathlib import Path

from capture_activity import (
    index_metadata_matches,
    load_capture_activity,
    mark_capture_events_indexed,
    record_capture_event,
)


class CaptureActivityTests(unittest.TestCase):
    def test_legacy_current_catalog_can_be_marked_without_model_reprocessing(self):
        expected = {
            "index_version": 3,
            "index_prompt_version": "library-batch-v3",
            "index_provider_id": "vision",
            "classification_index_complete": True,
        }
        legacy_catalog = {
            "index_version": 3,
            "index_prompt_version": "library-batch-v3",
            "index_provider_id": "vision",
        }
        self.assertTrue(index_metadata_matches(legacy_catalog, expected))
        legacy_catalog["index_provider_id"] = "other-vision"
        self.assertFalse(index_metadata_matches(legacy_catalog, expected))

    def test_duplicate_capture_is_retained_until_index_dedupes_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record_capture_event(
                root,
                category="sigh",
                filename="sigh_0001.png",
                digest="abc",
                status="duplicate",
                duplicate_of="sigh/sigh_0001.png",
            )

            data = load_capture_activity(root)
            self.assertEqual(data["events"][0]["status"], "duplicate")
            self.assertEqual(data["events"][0]["duplicate_of"], "sigh/sigh_0001.png")

            changed = mark_capture_events_indexed(
                root, category="sigh", digests={"abc"}
            )
            self.assertEqual(changed, 1)
            self.assertEqual(load_capture_activity(root)["events"][0]["status"], "deduped")

            saved = json.loads((root / "capture_activity.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], 1)


if __name__ == "__main__":
    unittest.main()
