"""Single-source contract for the allowed image extension set."""

from __future__ import annotations

import unittest

from backend.semantic_models import IMAGE_EXTENSIONS as SEMANTIC_IMAGE_EXTENSIONS
from infrastructure.storage_policy import IMAGE_EXTENSIONS as POLICY_IMAGE_EXTENSIONS
from storage import IMAGE_EXTENSIONS as STORAGE_IMAGE_EXTENSIONS


class ImageExtensionPolicyTests(unittest.TestCase):
    def test_storage_extension_set_matches_policy_single_source(self):
        self.assertEqual(STORAGE_IMAGE_EXTENSIONS, POLICY_IMAGE_EXTENSIONS)

    def test_semantic_extension_set_matches_policy_single_source(self):
        self.assertEqual(SEMANTIC_IMAGE_EXTENSIONS, frozenset(POLICY_IMAGE_EXTENSIONS))


if __name__ == "__main__":
    unittest.main()
