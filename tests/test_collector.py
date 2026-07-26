import unittest

from collector import (
    configured_provider_id,
    explicit_meme_request,
    extract_meme_markers,
    extract_image_sources,
    event_identity,
    normalize_category,
    parse_model_json,
    strip_meme_markers,
    whitelist_allows,
)


class FakeEvent:
    def __init__(self, group_id="123", umo="qq:GroupMessage:123"):
        self.group_id = group_id
        self.unified_msg_origin = umo

class CollectorTests(unittest.TestCase):
    def test_event_identity_uses_message_id(self):
        first = FakeEvent()
        second = FakeEvent()
        first.message_id = "message-42"
        second.message_id = "message-42"

        self.assertEqual(event_identity(first), event_identity(second))

    def test_event_identity_changes_for_different_messages(self):
        first = FakeEvent()
        second = FakeEvent()
        first.message_id = "message-42"
        second.message_id = "message-43"

        self.assertNotEqual(event_identity(first), event_identity(second))

    def test_provider_id_uses_override_then_fallback(self):
        config = {"scene_provider_id": "scene-model"}

        self.assertEqual(
            configured_provider_id(config, "reply_scene_provider_id", "scene_provider_id"),
            "scene-model",
        )
        config["reply_scene_provider_id"] = "reply-model"
        self.assertEqual(
            configured_provider_id(config, "reply_scene_provider_id", "scene_provider_id"),
            "reply-model",
        )

    def test_empty_whitelist_allows_every_group(self):
        self.assertTrue(whitelist_allows(FakeEvent(), []))

    def test_whitelist_matches_group_id_or_umo(self):
        self.assertTrue(whitelist_allows(FakeEvent(), ["123"]))
        self.assertTrue(whitelist_allows(FakeEvent(), ["qq:GroupMessage:123"]))
        self.assertFalse(whitelist_allows(FakeEvent(), ["456"]))

    def test_parse_json_from_code_fence(self):
        result = parse_model_json('```json\n{"category": "happy"}\n```')
        self.assertEqual(result["category"], "happy")

    def test_parse_batch_json_items(self):
        result = parse_model_json(
            '{"items":[{"id":"image_0","emotion":"happy"},{"id":"image_1","emotion":"shy"}]}'
        )
        self.assertEqual([item["id"] for item in result["items"]], ["image_0", "image_1"])

    def test_parse_model_python_dict_fallback(self):
        result = parse_model_json("{'items': [{'id': 'image_0', 'tags': ['晚安']}]}")
        self.assertEqual(result["items"][0]["id"], "image_0")

    def test_invalid_category_falls_back_and_rejects_path(self):
        allowed = {"happy", "confused"}
        self.assertEqual(normalize_category("../../tmp", allowed), "confused")
        self.assertEqual(normalize_category("开心", allowed), "happy")
        self.assertEqual(normalize_category("unknown", allowed), "confused")
        self.assertEqual(
            normalize_category("unknown", {"happy", "../escape"}, "../escape"),
            "happy",
        )

    def test_extract_image_sources_only_returns_image_components(self):
        components = [
            {"type": "plain", "text": "看图"},
            {"type": "image", "url": "https://example.test/a.png"},
            {"type": "image", "file": "base64://abc"},
        ]
        self.assertEqual(
            extract_image_sources(components),
            ["https://example.test/a.png", "base64://abc"],
        )

    def test_strip_meme_manager_markers(self):
        self.assertEqual(strip_meme_markers("你好 &&happy&& 世界 &&unknown&&"), "你好  世界")

    def test_extract_meme_markers_deduplicates_categories(self):
        self.assertEqual(
            extract_meme_markers("&&shy&& text &&happy&& &&shy&&"),
            ["shy", "happy"],
        )

    def test_explicit_meme_request_bypasses_automatic_probability(self):
        self.assertTrue(explicit_meme_request("可以发一下你的表情包库里的笨蛋表情吗"))
        self.assertTrue(explicit_meme_request("给我来一张图"))
        self.assertFalse(explicit_meme_request("今天的图片说明很清楚"))
        self.assertFalse(explicit_meme_request("不要发图片"))


if __name__ == "__main__":
    unittest.main()
