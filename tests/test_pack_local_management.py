import tempfile
import unittest
from pathlib import Path

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

from meme_manager_master.backend.category_manager import CategoryManager


class PackLocalManagementTests(unittest.TestCase):
    def test_category_manager_can_update_selected_pack_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir) / "selected-pack"
            (pack_dir / "memes").mkdir(parents=True)
            manager = CategoryManager(pack_dir)

            self.assertTrue(manager.update_description("happy", "Selected pack"))
            self.assertIn("Selected pack", manager.get_descriptions().values())
            self.assertEqual(
                (pack_dir / "memes_data.json").read_text(encoding="utf-8").count(
                    "Selected pack"
                ),
                1,
            )
            self.assertTrue((pack_dir / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
