import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ImagePreviewUiTests(unittest.TestCase):
    def test_modal_consumes_the_all_settled_preview_result(self):
        source = (ROOT / "pages" / "a_manage" / "emoji.js").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "const [previewResult] = await Promise.allSettled([previewRequest]);",
            source,
        )
        self.assertIn("previewResult.status === \"rejected\"", source)
        self.assertIn(
            "window.MemeManagerUI.state.imagePreviewImg.src = previewResult.value;",
            source,
        )


if __name__ == "__main__":
    unittest.main()
