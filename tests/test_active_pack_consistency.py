import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.fakes import FakeContext, install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

from meme_manager_master.capture import CaptureMixin  # noqa: E402
from meme_manager_master.storage import MemeStore  # noqa: E402


class ActivePackConsistencyTests(unittest.TestCase):
    def test_store_from_astrbot_resolves_active_pack_when_called(self):
        """Catch a store factory that retains ACTIVE_PACK_DIR from module import."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_pack = root / "first"
            second_pack = root / "second"

            with patch(
                "meme_manager_master.config.get_active_pack_paths",
                return_value={"pack_dir": first_pack},
            ):
                first_store = MemeStore.from_astrbot()
            with patch(
                "meme_manager_master.config.get_active_pack_paths",
                return_value={"pack_dir": second_pack},
            ):
                second_store = MemeStore.from_astrbot()

            self.assertEqual(first_store.root, first_pack.resolve())
            self.assertEqual(second_store.root, second_pack.resolve())

    def test_active_pack_refresh_rebinds_capture_and_selection_collaborators(self):
        """Catch capture or automatic selection retaining the prior pack's store."""
        with tempfile.TemporaryDirectory() as temp_dir:
            next_pack = Path(temp_dir) / "next-pack"
            mixin = CaptureMixin(FakeContext(), {})

            with patch(
                "meme_manager_master.backend.pack_resolver.resolve_pack_context",
                return_value={"pack_dir": next_pack},
            ):
                changed = mixin._refresh_store_for_active_pack()

            self.assertTrue(changed)
            self.assertEqual(mixin.store.root, next_pack.resolve())
            self.assertIs(mixin.capture_pipeline.store, mixin.store)
            self.assertIs(mixin.meme_selection.store, mixin.store)


if __name__ == "__main__":
    unittest.main()
