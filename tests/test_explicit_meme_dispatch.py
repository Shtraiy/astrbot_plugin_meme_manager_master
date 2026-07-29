import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ExplicitMemeDispatchTests(unittest.TestCase):
    def test_explicit_request_is_handled_before_reference_prompt_injection(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("await CaptureMixin.on_llm_request", source)
        self.assertNotIn("MemeSender.inject_meme_prompt", source)

    def test_capture_llm_hook_dispatches_explicit_request(self):
        source = (ROOT / "capture.py").read_text(encoding="utf-8")
        hook = source.index("async def on_llm_request")
        explicit = source.index("await self._handle_explicit_meme_request", hook)
        self.assertLess(explicit, source.index("tool_set =", hook))

    def test_explicit_request_is_available_to_decorating_fallback(self):
        source = (ROOT / "capture.py").read_text(encoding="utf-8")
        self.assertIn("self._remember_explicit_request(event)", source)
        self.assertIn("self._explicit_request_active(event)", source)
        decorating = source.index("async def on_decorating_result")
        self.assertLess(
            source.index("_explicit_request_active(event)", decorating),
            source.index("_rewrite_unverified_meme_claim", decorating),
        )

    def test_explicit_result_is_restored_if_agent_continuation_overwrites_it(self):
        source = (ROOT / "capture.py").read_text(encoding="utf-8")
        self.assertIn("self._forced_meme_results", source)
        self.assertIn("_restore_forced_meme_result", source)
        self.assertIn("event.stop_event()", source)

    def test_new_explicit_message_can_reclaim_a_reused_event_identity(self):
        source = (ROOT / "capture.py").read_text(encoding="utf-8")
        claim = source.index("async def _claim_auto_send")
        self.assertIn("explicit_handled", source[claim : claim + 900])
        on_message = source.index("async def on_message")
        self.assertIn(
            "_meme_manager_master_explicit_handled",
            source[on_message : on_message + 900],
        )


if __name__ == "__main__":
    unittest.main()
