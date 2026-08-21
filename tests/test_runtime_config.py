import json
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from runtime_config import PluginConfig, bool_value, float_value, int_value


ROOT = Path(__file__).parents[1]


class PluginConfigDefaultsTests(unittest.TestCase):
    def test_defaults_match_runtime_contract(self):
        config = PluginConfig.from_mapping({})
        self.assertTrue(config.enabled)
        self.assertEqual(config.group_whitelist, ())
        self.assertEqual(config.vision_provider_id, "")
        self.assertEqual(config.scene_provider_id, "")
        self.assertFalse(hasattr(config, "reply_scene_provider_id"))
        self.assertTrue(config.only_capture_memes)
        self.assertEqual(config.meme_rejection_confidence, 0.7)
        self.assertEqual(config.max_images_per_message, 2)
        self.assertEqual(config.max_concurrent, 2)
        self.assertEqual(config.max_image_size_mb, 10)
        self.assertEqual(config.download_timeout, 20)
        self.assertTrue(config.auto_send_enabled)
        self.assertEqual(config.auto_send_probability, 50)
        self.assertEqual(config.auto_send_cooldown, 30)
        self.assertTrue(config.llm_tool_enabled)
        self.assertEqual(config.auto_send_candidate_limit, 8)
        self.assertEqual(config.meme_repeat_window, 300)
        self.assertEqual(config.meme_follow_up_window, 300)
        self.assertFalse(config.proactive_send_after_steal)
        self.assertTrue(config.perceptual_dedupe_enabled)
        self.assertEqual(config.perceptual_duplicate_threshold, 6)
        self.assertFalse(config.library_index_enabled)
        self.assertEqual(config.library_index_provider_id, "")
        self.assertEqual(config.library_index_batch_size, 6)
        self.assertEqual(config.library_index_progress_step, 5)
        self.assertTrue(config.library_index_rename_files)
        self.assertEqual(config.health_check_interval, 300)
        self.assertEqual(config.fallback_category, "confused")
        self.assertEqual(config.local_image_roots, ())


class PluginConfigBoundaryTests(unittest.TestCase):
    def test_out_of_range_values_are_clamped(self):
        config = PluginConfig.from_mapping(
            {
                "max_images_per_message": 99,
                "max_concurrent": -4,
                "meme_rejection_confidence": 2.5,
                "auto_send_probability": -1,
                "health_check_interval": 5,
            }
        )
        self.assertEqual(config.max_images_per_message, 6)
        self.assertEqual(config.max_concurrent, 1)
        self.assertEqual(config.meme_rejection_confidence, 1.0)
        self.assertEqual(config.auto_send_probability, 0)
        self.assertEqual(config.health_check_interval, 10)

    def test_invalid_types_fall_back_to_defaults(self):
        config = PluginConfig.from_mapping(
            {
                "max_images_per_message": "abc",
                "auto_send_probability": {"nested": 1},
                "enabled": None,
            }
        )
        self.assertEqual(config.max_images_per_message, 2)
        self.assertEqual(config.auto_send_probability, 50)
        self.assertTrue(config.enabled)

    def test_list_fields_become_tuples(self):
        config = PluginConfig.from_mapping(
            {"group_whitelist": ["10001", "10002"], "local_image_roots": "E:/memes\nD:/pics"}
        )
        self.assertEqual(config.group_whitelist, ("10001", "10002"))
        self.assertEqual(config.local_image_roots, ("E:/memes", "D:/pics"))
        with self.assertRaises(AttributeError):
            config.group_whitelist.append("10003")

    def test_llm_tool_enabled_parses_explicit_false(self):
        self.assertFalse(
            PluginConfig.from_mapping({"llm_tool_enabled": False}).llm_tool_enabled
        )

    def test_legacy_nested_provider_is_used_when_flat_key_is_absent(self):
        config = PluginConfig.from_mapping({"semantic": {"vision_provider_id": "legacy-vision"}})
        self.assertEqual(config.vision_provider_id, "legacy-vision")

    def test_primary_flat_key_wins_over_legacy_path(self):
        config = PluginConfig.from_mapping(
            {
                "vision_provider_id": "primary-vision",
                "semantic": {"vision_provider_id": "legacy-vision"},
            }
        )
        self.assertEqual(config.vision_provider_id, "primary-vision")

    def test_config_is_frozen(self):
        config = PluginConfig.from_mapping({})
        with self.assertRaises(FrozenInstanceError):
            config.enabled = False


class PluginConfigHelpersTests(unittest.TestCase):
    def test_bool_value_parses_strings_like_runtime(self):
        self.assertFalse(bool_value("0", True))
        self.assertFalse(bool_value("false", True))
        self.assertFalse(bool_value("", True))
        self.assertTrue(bool_value("1", False))
        self.assertTrue(bool_value("yes", False))
        self.assertEqual(bool_value(1, False), True)
        self.assertEqual(bool_value("maybe", True), True)

    def test_int_float_value_reject_bools(self):
        self.assertEqual(int_value(True, 2, 1, 6), 2)
        self.assertEqual(float_value(False, 50.0, 0, 100), 50.0)


class PluginConfigSchemaTests(unittest.TestCase):
    def test_schema_exposes_only_daily_runtime_fields(self):
        schema = PluginConfig.to_schema()
        self.assertEqual(
            set(schema),
            {
                "enabled",
                "group_whitelist",
                "vision_provider_id",
                "scene_provider_id",
                "only_capture_memes",
                "auto_send_enabled",
                "auto_send_probability",
                "auto_send_cooldown",
                "llm_tool_enabled",
            },
        )

    def test_hidden_settings_and_deprecated_fallback_remain_compatible(self):
        config = PluginConfig.from_mapping(
            {
                "max_concurrent": 7,
                "library_index_enabled": True,
                "fallback_category": "happy",
            }
        )

        self.assertEqual(config.max_concurrent, 7)
        self.assertTrue(config.library_index_enabled)
        self.assertEqual(config.fallback_category, "happy")
        self.assertNotIn("max_concurrent", PluginConfig.to_schema())
        self.assertNotIn("library_index_enabled", PluginConfig.to_schema())
        self.assertNotIn("fallback_category", PluginConfig.to_schema())

    def test_generated_schema_matches_checked_in_file(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_conf_schema.py"), "--check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"schema drift: {result.stdout}\n{result.stderr}",
        )

    def test_checked_in_schema_json_is_valid_and_typed(self):
        schema = json.loads(
            (ROOT / "_conf_schema.json").read_text(encoding="utf-8")
        )
        for key, entry in schema.items():
            self.assertIn("type", entry)
            self.assertIn("default", entry)
            self.assertIn("description", entry)


if __name__ == "__main__":
    unittest.main()
