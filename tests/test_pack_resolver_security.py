import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.fakes import install_package_alias


install_package_alias()

from meme_manager_master.backend import pack_resolver  # noqa: E402


class PackResolverSecurityTests(unittest.TestCase):
    def test_pack_exists_rejects_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            packs_dir = Path(temp_dir) / "packs"
            outside_dir = Path(temp_dir) / "outside"
            packs_dir.mkdir()
            outside_dir.mkdir()
            with patch.object(pack_resolver, "PACKS_DIR", packs_dir):
                self.assertFalse(pack_resolver._pack_exists(str(outside_dir)))

    def test_get_pack_paths_rejects_parent_path(self):
        with self.assertRaises(ValueError):
            pack_resolver.get_pack_paths("../outside")


if __name__ == "__main__":
    unittest.main()
