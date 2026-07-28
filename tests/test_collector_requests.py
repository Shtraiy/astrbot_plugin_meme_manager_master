import unittest

from collector import (
    contains_meme_send_claim,
    explicit_meme_request,
    is_meme_follow_up_request,
    is_safe_remote_image_url,
    is_supported_image_source,
)


class CollectorRequestTests(unittest.TestCase):
    def test_descriptive_cat_meme_request_is_explicit(self):
        self.assertTrue(explicit_meme_request("再发一个可爱猫猫标签"))

    def test_descriptive_follow_up_is_explicit_with_recent_meme(self):
        self.assertTrue(
            is_meme_follow_up_request(
                "再发一个可爱猫猫标签",
                recent_meme=True,
            )
        )

    def test_non_meme_follow_up_targets_are_not_meme_requests(self):
        self.assertFalse(is_meme_follow_up_request("再发一个文件", recent_meme=True))
        self.assertFalse(
            is_meme_follow_up_request("别再发一个猫猫表情", recent_meme=True)
        )

    def test_meme_send_claim_is_detected(self):
        self.assertTrue(contains_meme_send_claim("这个表情包发给你啦"))
        self.assertTrue(contains_meme_send_claim("新的猫猫也送给你了"))

    def test_non_claim_text_is_not_treated_as_receipt(self):
        self.assertFalse(contains_meme_send_claim("我可以发一个表情包给你吗？"))


    def test_remote_image_url_rejects_unsafe_upload_sources(self):
        self.assertFalse(is_safe_remote_image_url("http://127.0.0.1/internal.png"))
        self.assertFalse(is_safe_remote_image_url("https://user:secret@example.com/a.png"))
        self.assertFalse(is_safe_remote_image_url("ftp://example.com/a.png"))
        self.assertTrue(is_safe_remote_image_url("https://cdn.example.com/a.png"))

    def test_supported_image_source_rejects_unhandled_protocols(self):
        self.assertTrue(is_supported_image_source("https://cdn.example.com/a.png"))
        self.assertTrue(is_supported_image_source("file:///AstrBot/data/temp/a.png"))
        self.assertTrue(is_supported_image_source("data:image/png;base64,AAAA"))
        self.assertFalse(is_supported_image_source("ftp://example.com/a.png"))
        self.assertFalse(is_supported_image_source("javascript:alert(1)"))


if __name__ == "__main__":
    unittest.main()
