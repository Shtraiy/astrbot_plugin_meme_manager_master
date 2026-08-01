import unittest

from response_policy import success_reply_text


class CaptureDispatchBehaviorTests(unittest.TestCase):
    def test_explicit_success_does_not_generate_fixed_text(self):
        self.assertEqual(success_reply_text(None), "")

    def test_auto_send_keeps_the_original_visible_reply(self):
        reply = "这也太离谱了哈哈。"
        self.assertEqual(success_reply_text(reply), reply)

    def test_success_policy_never_uses_legacy_copy(self):
        values = [success_reply_text(), success_reply_text("原回复")]
        legacy = ("找到一个合适的表情包", "找到了一个合适的表情包")
        self.assertTrue(all(marker not in value for value in values for marker in legacy))


if __name__ == "__main__":
    unittest.main()
