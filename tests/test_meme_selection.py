import asyncio
import unittest
from pathlib import Path

from tests.fakes import FakeEvent, install_package_alias, install_runtime_stubs


install_runtime_stubs()
install_package_alias()

from meme_manager_master.meme_selection import MemeSelectionService  # noqa: E402


class _Store:
    def category_descriptions(self):
        return {"sad": "悲伤反应", "happy": "开心反应"}

    def load_catalog(self, category):
        return {"items": [{"filename": f"{category}.png"}]}

    def pick_indexed_image(self, category, repeat_window):
        return Path(f"{category}.png")


class _Config:
    auto_send_candidate_limit = 8
    meme_repeat_window = 0


class MemeSelectionBehaviorTests(unittest.TestCase):
    def _service(self, generate):
        return MemeSelectionService(
            store=_Store(),
            config=_Config(),
            generate=generate,
            event_text=lambda event: event.get_message_str(),
            image_details=lambda path: {
                "filename": path.name,
                "description": "",
                "emotion": path.stem,
            },
            model_bool=lambda value, default: bool(value)
            if value is not None
            else default,
        )

    def test_category_marker_is_only_a_hint(self):
        async def generate(*args, **kwargs):
            return '{"should_send":true,"category":"happy","confidence":0.9,"reason":"开心"}'

        service = self._service(generate)
        result = asyncio.run(
            service.choose(
                FakeEvent(message_text="普通聊天"),
                "这件事太好了。",
                force_send=False,
                preferred_categories=["sad"],
            )
        )

        self.assertEqual(result, Path("happy.png"))

    def test_model_can_reject_a_plain_text_reply(self):
        async def generate(*args, **kwargs):
            return '{"should_send":false,"category":"","confidence":0.9,"reason":"无明显情绪"}'

        service = self._service(generate)
        result = asyncio.run(
            service.choose(
                FakeEvent(message_text="生成自拍"),
                "已完成。",
                force_send=False,
            )
        )

        self.assertIsNone(result)

    def test_recent_context_is_included_as_scene_evidence(self):
        prompts = []

        async def generate(*args, **kwargs):
            prompts.append(args[1])
            return '{"should_send":false,"category":"","confidence":0.9,"reason":"no"}'

        service = self._service(generate)
        result = asyncio.run(
            service.choose(
                FakeEvent(message_text="follow-up"),
                "The image is ready.",
                context_text="[user] generated several images\n[assistant] feeling tired",
            )
        )

        self.assertIsNone(result)
        self.assertIn("recent_context", prompts[0])
        self.assertIn("generated several images", prompts[0])


if __name__ == "__main__":
    unittest.main()
