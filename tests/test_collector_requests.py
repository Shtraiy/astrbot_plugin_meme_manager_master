import unittest

from collector import (
    contains_meme_send_claim,
    explicit_meme_request,
    is_meme_follow_up_request,
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


if __name__ == "__main__":
    unittest.main()
