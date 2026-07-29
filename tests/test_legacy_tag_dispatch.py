import unittest
from pathlib import Path


class LegacyTagDispatchTests(unittest.TestCase):
    def test_main_does_not_dispatch_legacy_prompt_or_response_parser(self):
        source = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("MemeSender.inject_meme_prompt", source)
        self.assertNotIn("MemeSender.resp", source)
        self.assertIn("CaptureMixin.on_decorating_result", source)

    def test_legacy_semantic_config_cannot_start_vector_rebuilds(self):
        source = (Path(__file__).parents[1] / "manager_base.py").read_text(encoding="utf-8")
        self.assertIn("self.semantic_enabled = False", source)


if __name__ == "__main__":
    unittest.main()
