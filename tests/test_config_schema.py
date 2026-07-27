import json
import unittest
from pathlib import Path


class ConfigSchemaTests(unittest.TestCase):
    def test_metadata_points_to_the_plugin_repository(self):
        root = Path(__file__).resolve().parents[1]
        metadata = (root / "metadata.yaml").read_text(encoding="utf-8")

        repo_line = next(
            line for line in metadata.splitlines() if line.startswith("repo:")
        )
        self.assertEqual(
            repo_line,
            "repo: https://github.com/Shtraiy/astrbot_plugin_meme_stealer",
        )

    def test_plugin_display_name_is_meme_master(self):
        root = Path(__file__).resolve().parents[1]

        metadata = (root / "metadata.yaml").read_text(encoding="utf-8")
        readme = (root / "README.md").read_text(encoding="utf-8")

        self.assertIn("display_name:", metadata)
        self.assertIn("# AstrBot", readme)

    def _schema(self):
        root = Path(__file__).resolve().parents[1]
        return json.loads((root / "_conf_schema.json").read_text(encoding="utf-8"))

    def test_schema_uses_astrbot_plugin_config_shape(self):
        schema = self._schema()
        supported_types = {"string", "bool", "int", "float", "list", "object"}

        self.assertNotIn("properties", schema)
        self.assertNotIn("type", schema)
        for key, value in schema.items():
            self.assertIsInstance(value, dict, key)
            self.assertIn(value.get("type"), supported_types, key)

    def test_model_settings_use_astrbot_provider_selector(self):
        schema = self._schema()
        for key in (
            "vision_provider_id",
            "scene_provider_id",
            "reply_scene_provider_id",
            "library_index_provider_id",
        ):
            self.assertEqual(schema[key].get("_special"), "select_provider", key)

    def test_schema_exposes_all_runtime_settings(self):
        schema = self._schema()
        self.assertEqual(
            set(schema),
            {
                "enabled",
                "group_whitelist",
                "vision_provider_id",
                "scene_provider_id",
                "reply_scene_provider_id",
                "only_capture_memes",
                "fallback_category",
                "max_images_per_message",
                "max_image_size_mb",
                "max_concurrent",
                "download_timeout",
                "health_check_interval",
                "auto_send_enabled",
                "auto_send_probability",
                "auto_send_cooldown",
                "auto_send_candidate_limit",
                "library_index_provider_id",
                "library_index_enabled",
                "library_index_progress_step",
                "library_index_batch_size",
                "library_index_rename_files",
                "perceptual_dedupe_enabled",
                "perceptual_duplicate_threshold",
                "meme_rejection_confidence",
                "local_image_roots",
            },
        )
        self.assertFalse(schema["library_index_enabled"]["default"])
        self.assertEqual(schema["library_index_batch_size"]["type"], "int")
        self.assertEqual(schema["library_index_batch_size"]["default"], 6)
        self.assertEqual(schema["library_index_batch_size"]["min"], 1)
        self.assertEqual(schema["library_index_batch_size"]["max"], 12)


if __name__ == "__main__":
    unittest.main()
