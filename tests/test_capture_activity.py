import json
import tempfile
import unittest
from pathlib import Path

from capture_activity import (
    index_metadata_matches,
    load_capture_activity,
    mark_capture_events_blacklisted,
    mark_capture_events_ignored,
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

    def test_ignoring_digest_updates_all_duplicate_events_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "meme.png"
            image.write_bytes(b"keep this file")
            for category, status in (("happy", "duplicate"), ("sad", "duplicate"), ("angry", "pending")):
                record_capture_event(
                    root,
                    category=category,
                    filename=image.name,
                    digest="a" * 64,
                    status=status,
                    captured_at=200,
                )
            record_capture_event(
                root,
                category="happy",
                filename=image.name,
                digest="b" * 64,
                status="indexed",
                captured_at=201,
            )

            changed = mark_capture_events_ignored(
                root, digests={"a" * 64}, ignored_at=1234567890
            )

            self.assertEqual(changed, 2)
            events = load_capture_activity(root)["events"]
            self.assertEqual([event["status"] for event in events], ["ignored", "ignored", "pending", "indexed"])
            self.assertEqual(events[0]["ignored_at"], 1234567890)
            self.assertEqual(image.read_bytes(), b"keep this file")

    def test_blacklisting_digest_resolves_duplicate_events_without_touching_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for status in ("duplicate", "pending"):
                record_capture_event(
                    root,
                    category="happy",
                    filename="meme.png",
                    digest="a" * 64,
                    status=status,
                )

            changed = mark_capture_events_blacklisted(root, digests={"a" * 64})

            self.assertEqual(changed, 1)
            self.assertEqual(
                [event["status"] for event in load_capture_activity(root)["events"]],
                ["blacklisted", "pending"],
            )


if __name__ == "__main__":
    unittest.main()
