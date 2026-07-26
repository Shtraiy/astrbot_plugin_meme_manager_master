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
        for key in ("vision_provider_id", "scene_provider_id"):
            self.assertEqual(schema[key].get("_special"), "select_provider", key)

    def test_schema_exposes_only_core_settings(self):
        schema = self._schema()
        self.assertEqual(
            set(schema),
            {
                "enabled",
                "group_whitelist",
                "vision_provider_id",
                "scene_provider_id",
                "only_capture_memes",
                "auto_send_enabled",
                "library_index_enabled",
            },
        )
        self.assertNotIn("perceptual_duplicate_threshold", schema)
        self.assertNotIn("library_index_batch_size", schema)


if __name__ == "__main__":
    unittest.main()
