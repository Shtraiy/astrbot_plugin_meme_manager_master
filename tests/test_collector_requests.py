import unittest

from collector import (
    contains_meme_send_claim,
    is_safe_remote_image_url,
    parse_model_json,
    should_block_agent_tool_for_meme_request,
    is_supported_image_source,
)


class CollectorRequestTests(unittest.TestCase):
    def test_model_json_ignores_thinking_object_and_trailing_text(self):
        response = (
            '<think>{"draft":{"invalid":true}}</think>\n'
            '{"items":[]}\n识别完成。'
        )

        self.assertEqual(parse_model_json(response), {"items": []})

    def test_model_json_accepts_fenced_json_with_trailing_text(self):
        response = '```json\n{"items":[]}\n```\n识别完成。'

        self.assertEqual(parse_model_json(response), {"items": []})

    def test_natural_language_does_not_activate_image_tool_guard(self):
        self.assertFalse(
            should_block_agent_tool_for_meme_request(
                "astrbot_execute_python",
                "再发一个可爱猫猫标签",
                guard_active=False,
            )
        )

    def test_real_meme_send_guard_still_blocks_image_tool(self):
        self.assertTrue(
            should_block_agent_tool_for_meme_request(
                "astrbot_execute_python",
                "生成自拍",
                guard_active=True,
            )
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
