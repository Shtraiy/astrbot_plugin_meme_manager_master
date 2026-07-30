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

    def test_retired_semantic_search_tool_is_not_registered(self):
        source = (Path(__file__).parents[1] / "manager_base.py").read_text(encoding="utf-8")
        self.assertNotIn('@llm_tool(name="search_memes")', source)
        self.assertNotIn("async def search_memes_tool", source)

    def test_request_path_removes_stale_search_memes_tool(self):
        source = (Path(__file__).parents[1] / "capture.py").read_text(encoding="utf-8")
        hook = source.index("async def on_llm_request")
        self.assertIn("_remove_retired_agent_tools", source[hook : hook + 1400])
        self.assertIn('remove_tool("search_memes")', source)

    def test_tool_path_blocks_retired_search_memes_tool(self):
        source = (Path(__file__).parents[1] / "capture.py").read_text(encoding="utf-8")
        hook = source.index("async def on_using_llm_tool")
        self.assertIn('tool_name == "search_memes"', source[hook : hook + 900])
        self.assertIn("blocked retired Agent tool", source[hook : hook + 900])


if __name__ == "__main__":
    unittest.main()
