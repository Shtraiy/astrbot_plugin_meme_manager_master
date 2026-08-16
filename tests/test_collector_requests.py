import unittest

from collector import (
    contains_meme_send_claim,
    is_safe_remote_image_url,
    parse_model_json,
    should_block_agent_tool_for_meme_request,
    should_skip_meme_result,
    is_supported_image_source,
)


def valid_meme_result(**overrides):
    result = {
        "is_meme": True,
        "confidence": 0.95,
        "meme_score": 85,
        "content_type": "reaction_meme",
        "has_expression": True,
        "is_screenshot": False,
        "is_chat_screenshot": False,
        "is_document": False,
        "is_ui": False,
        "is_photo": False,
        "is_webpage": False,
        "is_poster": False,
        "is_banner": False,
        "is_receipt": False,
    }
    result.update(overrides)
    return result


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

    def test_capture_classifier_accepts_only_high_confidence_meme_content(self):
        accepted = valid_meme_result()
        self.assertFalse(should_skip_meme_result(accepted))
        self.assertTrue(should_skip_meme_result({**accepted, "confidence": 0.69}))
        self.assertTrue(should_skip_meme_result({key: value for key, value in accepted.items() if key != "content_type"}))

    def test_capture_classifier_accepts_score_at_threshold(self):
        self.assertFalse(should_skip_meme_result(valid_meme_result(meme_score=70)))

    def test_capture_classifier_rejects_score_below_threshold(self):
        self.assertTrue(should_skip_meme_result(valid_meme_result(meme_score=69)))

    def test_capture_classifier_rejects_missing_or_invalid_score(self):
        for value in (None, True, False, "not-a-number", float("nan"), float("inf"), -1, 101):
            with self.subTest(value=value):
                result = valid_meme_result()
                if value is None:
                    result.pop("meme_score")
                else:
                    result["meme_score"] = value
                self.assertTrue(should_skip_meme_result(result))

    def test_capture_classifier_score_does_not_override_hard_rejections(self):
        self.assertTrue(should_skip_meme_result(valid_meme_result(meme_score=100, is_photo=True)))

    def test_capture_classifier_rejects_screenshots_documents_and_ordinary_photos(self):
        base = valid_meme_result(confidence=0.98)
        for field in (
            "is_screenshot",
            "is_chat_screenshot",
            "is_document",
            "is_ui",
            "is_photo",
            "is_webpage",
            "is_poster",
            "is_banner",
            "is_receipt",
        ):
            with self.subTest(field=field):
                self.assertTrue(should_skip_meme_result({**base, field: True}))
        for content_type in ("photo", "screenshot", "chat_screenshot", "document", "webpage", "ui"):
            with self.subTest(content_type=content_type):
                self.assertTrue(should_skip_meme_result({**base, "content_type": content_type}))
        self.assertTrue(should_skip_meme_result({**base, "has_expression": False}))


if __name__ == "__main__":
    unittest.main()
