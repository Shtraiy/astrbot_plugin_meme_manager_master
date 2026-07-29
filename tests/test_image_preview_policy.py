import unittest

from storage import image_preview_mode


class ImagePreviewPolicyTests(unittest.TestCase):
    def test_large_gif_uses_thumbnail_preview(self):
        self.assertEqual(
            image_preview_mode(
                file_size=9_004_665,
                mime_type="image/gif",
                requested_size="preview",
                raw_preview_limit=8 * 1024 * 1024,
                source_limit=32 * 1024 * 1024,
            ),
            "thumbnail",
        )

    def test_small_gif_keeps_original_preview_and_oversized_source_is_rejected(self):
        self.assertEqual(
            image_preview_mode(
                file_size=1024,
                mime_type="image/gif",
                requested_size="preview",
                raw_preview_limit=8 * 1024 * 1024,
                source_limit=32 * 1024 * 1024,
            ),
            "original",
        )
        self.assertEqual(
            image_preview_mode(
                file_size=33 * 1024 * 1024,
                mime_type="image/gif",
                requested_size="preview",
                raw_preview_limit=8 * 1024 * 1024,
                source_limit=32 * 1024 * 1024,
            ),
            "reject",
        )


if __name__ == "__main__":
    unittest.main()
