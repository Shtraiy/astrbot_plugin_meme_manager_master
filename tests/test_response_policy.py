import unittest

from response_policy import success_reply_text


class ResponsePolicyTests(unittest.TestCase):
    def test_explicit_image_success_has_no_announcement(self):
        self.assertEqual(success_reply_text(), "")

    def test_existing_agent_reply_is_preserved_verbatim(self):
        original = "当然可以，今天也要开心。"
        self.assertEqual(success_reply_text(original), original)

    def test_whitespace_only_reply_is_treated_as_empty(self):
        self.assertEqual(success_reply_text(" \n\t "), "")


if __name__ == "__main__":
    unittest.main()
