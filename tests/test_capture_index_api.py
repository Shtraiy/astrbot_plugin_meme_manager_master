import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()


if "quart" not in sys.modules:
    quart = types.ModuleType("quart")

    class _Request:
        args = {}

        async def get_json(self):
            return {}

    quart.request = _Request()
    quart.jsonify = lambda payload: payload
    quart.send_file = lambda path: ("file", path)
    sys.modules["quart"] = quart

    werkzeug = types.ModuleType("werkzeug")
    exceptions = types.ModuleType("werkzeug.exceptions")
    exceptions.RequestEntityTooLarge = type("RequestEntityTooLarge", (Exception,), {})
    werkzeug.exceptions = exceptions
    sys.modules["werkzeug"] = werkzeug
    sys.modules["werkzeug.exceptions"] = exceptions
    utils = types.ModuleType("werkzeug.utils")
    utils.secure_filename = lambda value: str(value or "")
    werkzeug.utils = utils
    sys.modules["werkzeug.utils"] = utils
    sys.modules["requests"] = types.ModuleType("requests")

from capture_activity import record_capture_event
from meme_manager_master.mixins import capture_index_api
from meme_manager_master.mixins.capture_index_api import CaptureIndexAPIMixin
from storage import MemeStore


class CaptureIndexApiTests(unittest.TestCase):
    def test_workspace_returns_recent_indexed_and_pending_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            indexed = store.save_image(b"indexed-image", "happy", ".png").path
            pending = store.save_image(b"pending-image", "happy", ".png").path
            catalog = store.load_catalog("happy")
            for item in catalog["items"]:
                if item["filename"] == indexed.name:
                    item["indexed"] = True
                else:
                    item["indexed"] = False
            store.write_catalog(
                "happy",
                catalog["items"],
                {"classification_index_complete": False},
            )
            record_capture_event(
                pack_dir,
                category="happy",
                filename=pending.name,
                digest=store.image_digest(pending),
                status="pending",
                captured_at=200,
            )

            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance._library_index_state = {"status": "idle"}
            instance._safe_image_filename = lambda value: Path(value).suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
            }
            instance.store = store

            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent):
                workspace = instance._capture_workspace_for_pack("pack")

        self.assertEqual(workspace["summary"]["indexed"], 1)
        self.assertEqual(workspace["summary"]["pending"], 1)
        self.assertEqual(workspace["indexed_items"][0]["filename"], indexed.name)
        self.assertEqual(workspace["pending_items"][0]["filename"], pending.name)

    def test_workspace_does_not_expose_absolute_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "pack"
            store = MemeStore(pack_dir)
            image = store.save_image(b"image", "happy", ".png").path
            instance = CaptureIndexAPIMixin.__new__(CaptureIndexAPIMixin)
            instance._library_index_state = {}
            instance._safe_image_filename = lambda value: True
            with patch.object(capture_index_api, "PACKS_DIR", pack_dir.parent):
                workspace = instance._capture_workspace_for_pack("pack")

        serialized = json.dumps(workspace, ensure_ascii=False)
        self.assertNotIn(str(pack_dir), serialized)
        self.assertIn(f"memes/happy/{image.name}", serialized)


if __name__ == "__main__":
    unittest.main()
