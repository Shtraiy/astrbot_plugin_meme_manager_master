import asyncio
import json
import unittest
from types import SimpleNamespace

from tests.fakes import FakeContext, FakeEvent, install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

from meme_manager_master.capture import CaptureMixin  # noqa: E402
from meme_manager_master.collector import collect_recent_scene_context  # noqa: E402


class SceneContextTests(unittest.TestCase):
    def test_keeps_the_last_three_turns_and_discards_older_messages(self):
        request = SimpleNamespace(
            contexts=[
                {"role": "user", "content": "old-user"},
                {"role": "assistant", "content": "old-assistant"},
                {"role": "user", "content": "user-1"},
                {"role": "assistant", "content": "assistant-1"},
                {"role": "user", "content": "user-2"},
                {"role": "assistant", "content": "assistant-2"},
                {"role": "user", "content": "user-3"},
                {"role": "assistant", "content": "assistant-3"},
            ]
        )

        result = collect_recent_scene_context(request)

        self.assertNotIn("old-user", result)
        self.assertNotIn("old-assistant", result)
        self.assertIn("[user] user-1", result)
        self.assertIn("[assistant] assistant-3", result)

    def test_ignores_non_text_content_and_applies_size_limits(self):
        request = SimpleNamespace(
            messages=[
                {"role": "user", "content": "x" * 500},
                {"role": "assistant", "content": {"type": "image", "url": "secret"}},
                {"role": "assistant", "content": "visible"},
            ]
        )

        result = collect_recent_scene_context(request)

        self.assertLessEqual(len(result), 1800)
        self.assertIn("[user] " + "x" * 300, result)
        self.assertNotIn("secret", result)
        self.assertIn("[assistant] visible", result)

    def test_drops_system_and_tool_messages_from_scene_context(self):
        request = SimpleNamespace(
            contexts=[
                {"role": "system", "content": "internal policy"},
                {"role": "tool", "content": "tool output"},
                {"role": "user", "content": "visible user"},
                {"role": "assistant", "content": "visible assistant"},
            ]
        )

        result = collect_recent_scene_context(request)

        self.assertNotIn("internal policy", result)
        self.assertNotIn("tool output", result)
        self.assertIn("visible user", result)
        self.assertIn("visible assistant", result)

    def test_accepts_serialized_history_and_normalizes_common_roles(self):
        request = SimpleNamespace(
            contexts=json.dumps(
                [
                    {"role": "human", "content": "human message"},
                    {"role": "bot", "content": "bot reply"},
                ]
            )
        )

        result = collect_recent_scene_context(request)

        self.assertIn("[user] human message", result)
        self.assertIn("[assistant] bot reply", result)

    def test_llm_request_stores_context_for_the_final_scene_decision(self):
        request = SimpleNamespace(
            history=[
                {"role": "user", "content": "连续生成了几张图"},
                {"role": "assistant", "content": "已经生成完成"},
            ]
        )
        async def scenario():
            event = FakeEvent(message_text="再来一张")
            mixin = CaptureMixin(FakeContext(), {})
            await mixin.on_llm_request(event, request)
            return event.get_extra("meme_manager_master_scene_context")

        result = asyncio.run(scenario())

        self.assertIn("连续生成了几张图", result)


if __name__ == "__main__":
    unittest.main()
