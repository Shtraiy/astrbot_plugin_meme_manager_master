import unittest

from backend.tagging import (
    normalize_primary_category,
    normalize_semantic_tags,
    normalize_tags,
)


class TaggingTests(unittest.TestCase):
    def test_normalize_tags_maps_aliases_and_deduplicates(self):
        self.assertEqual(
            normalize_tags(["生气", "愤怒", "吃惊"]),
            ["愤怒", "震惊"],
        )

    def test_normalize_tags_limits_results_and_uses_other(self):
        self.assertEqual(
            normalize_tags(["愤怒", "震惊", "疑惑", "无语", "嘲讽", "未知长句"]),
            ["愤怒", "震惊", "疑惑", "无语", "嘲讽"],
        )
        self.assertEqual(normalize_tags(["未知长句"]), ["其他"])
        self.assertEqual(normalize_tags(["其他", "震惊"]), ["震惊"])

    def test_normalize_tags_allows_six_fixed_tags(self):
        self.assertEqual(
            normalize_tags(["开心", "愤怒", "悲伤", "震惊", "疑惑", "尴尬", "害怕"]),
            ["开心", "愤怒", "悲伤", "震惊", "疑惑", "尴尬"],
        )

    def test_normalize_tags_accepts_delimited_text(self):
        self.assertEqual(
            normalize_tags("生气，吃惊 / 无语"),
            ["愤怒", "震惊", "无语"],
        )

    def test_primary_category_uses_small_stable_vocabulary(self):
        self.assertEqual(normalize_primary_category("无奈"), "无奈")
        self.assertEqual(normalize_primary_category("sigh"), "无奈")
        self.assertEqual(normalize_primary_category("嘲讽"), "吐槽")
        self.assertEqual(normalize_primary_category("meow"), "卖萌")
        self.assertIsNone(normalize_primary_category("工作"))
        self.assertIsNone(normalize_primary_category("吃瓜"))

    def test_semantic_tags_are_auxiliary_and_capped_at_two(self):
        self.assertEqual(
            normalize_semantic_tags(["反问", "认错", "额外标签"]),
            ["反问", "认错"],
        )


if __name__ == "__main__":
    unittest.main()
