import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IndexedEmojiThumbnailCardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "pages" / "a_manage" / "capture-index.js").read_text(
            encoding="utf-8"
        )
        cls.style = (ROOT / "pages" / "a_manage" / "capture-index.css").read_text(
            encoding="utf-8"
        )

    def test_cards_render_thumbnail_with_accessible_filename_and_status(self):
        self.assertIn('className = "card-thumbnail"', self.script)
        self.assertIn('image.loading = "lazy"', self.script)
        self.assertIn('card.title = item.filename || "未命名图片"', self.script)
        self.assertIn("thumbnail-placeholder", self.script)
        self.assertIn("thumbnail-error", self.script)

    def test_thumbnail_uses_preview_api_and_original_preview_stays_original(self):
        self.assertIn('apiGet("meme_image_data"', self.script)
        self.assertIn('size: "preview"', self.script)
        self.assertIn('size: "original"', self.script)
        self.assertIn("data.data_url", self.script)

    def test_failed_thumbnail_can_be_retried_without_removing_card_preview(self):
        self.assertIn("loadThumbnail(item, image, card)", self.script)
        self.assertIn('card.classList.contains("thumbnail-error")', self.script)
        self.assertIn('image.addEventListener("error"', self.script)
        self.assertIn("点击重试", self.script)
        self.assertIn('card.addEventListener("click"', self.script)

    def test_thumbnail_styles_cover_grid_ratio_focus_and_reduced_motion(self):
        self.assertIn("grid-template-columns: repeat(auto-fill", self.style)
        self.assertIn(".card-thumbnail", self.style)
        self.assertIn("aspect-ratio:", self.style)
        self.assertIn(":focus-visible", self.style)
        self.assertIn("prefers-reduced-motion", self.style)


if __name__ == "__main__":
    unittest.main()
