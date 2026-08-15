import unittest
from pathlib import Path

from tests.fakes import install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

from meme_manager_master.capture import (
    LIBRARY_INDEX_PROMPT_VERSION,
    LIBRARY_INDEX_VERSION,
    VISION_SYSTEM_PROMPT,
    _library_batch_system_prompt,
    _library_single_system_prompt,
)
from meme_manager_master.capture_pipeline import VISION_BATCH_SYSTEM_PROMPT
from meme_manager_master.indexing import normalize_library_results


class PrimarySemanticIndexTests(unittest.TestCase):
    def test_normalized_library_result_keeps_primary_and_image_text_semantics(self):
        path = Path("awkward.png")
        result = normalize_library_results(
            [
                {
                    "id": "image_0",
                    "primary_category": "尴尬",
                    "semantic_tags": ["认错", "反问", "多余"],
                    "semantic_summary": "角色发现自己刚才说错话，表情窘迫。",
                    "visible_text": "但是不是你自己发的吗",
                    "text_meaning": "反问对方并指出对方前后矛盾，带有自嘲和尴尬。",
                    "use_cases": ["承认口误", "尴尬地反问"],
                    "avoid_cases": ["真诚赞同", "单纯开心"],
                    "classification_confidence": 0.92,
                }
            ],
            [path],
        )[path]

        self.assertEqual(result["primary_category"], "尴尬")
        self.assertEqual(result["semantic_tags"], ["认错", "反问"])
        self.assertEqual(result["visible_text"], "但是不是你自己发的吗")
        self.assertEqual(result["text"], result["visible_text"])
        self.assertTrue(result["text_meaning"])
        self.assertEqual(result["use_cases"], ["承认口误", "尴尬地反问"])
        self.assertEqual(result["avoid_cases"], ["真诚赞同", "单纯开心"])
        self.assertEqual(result["classification_confidence"], 0.92)

    def test_invalid_primary_result_is_marked_for_reindex(self):
        path = Path("unknown.png")
        result = normalize_library_results(
            [{"id": "image_0", "primary_category": "工作", "tags": ["开心"]}],
            [path],
        )[path]

        self.assertEqual(result["primary_category"], "")
        self.assertEqual(result["primary_category_status"], "needs_reindex")

    def test_library_prompts_use_primary_and_text_semantic_contract(self):
        batch_prompt = _library_batch_system_prompt("固定标签")
        single_prompt = _library_single_system_prompt("固定标签")

        for prompt in (batch_prompt, single_prompt):
            self.assertIn("主分类", prompt)
            self.assertIn("visible_text", prompt)
            self.assertIn("text_meaning", prompt)
            self.assertIn("avoid_cases", prompt)
            self.assertIn("semantic_tags", prompt)
            self.assertIn("开心、悲伤、尴尬、无奈、疑惑、震惊、愤怒、吐槽、赞同、拒绝、卖萌、围观", prompt)
        self.assertNotIn("工作", batch_prompt)
        self.assertGreaterEqual(LIBRARY_INDEX_VERSION, 4)
        self.assertIn("semantic-primary", LIBRARY_INDEX_PROMPT_VERSION)

    def test_capture_prompts_require_strict_content_type_and_rejection_flags(self):
        for prompt in (VISION_SYSTEM_PROMPT, VISION_BATCH_SYSTEM_PROMPT):
            self.assertIn("content_type", prompt)
            self.assertIn("is_screenshot", prompt)
            self.assertIn("is_chat_screenshot", prompt)
            self.assertIn("is_document", prompt)
            self.assertIn("is_ui", prompt)
            self.assertIn("rejection_reason", prompt)
            self.assertIn("高置信度", prompt)


if __name__ == "__main__":
    unittest.main()
