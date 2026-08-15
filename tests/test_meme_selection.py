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


class _CandidateStore:
    def __init__(self):
        self.selected_filenames = None
        self.items = [
            {
                "id": "meme-safe",
                "filename": "safe.png",
                "description": "低头认错的反应",
                "emotion": "尴尬",
                "text": "",
                "tags": ["尴尬"],
                "indexed": True,
            },
            {
                "id": "meme-caption",
                "filename": "caption.png",
                "description": "带有突兀配字的反应",
                "emotion": "尴尬",
                "text": "这是一段不适合当前语境的配字",
                "tags": ["尴尬"],
                "indexed": True,
            },
        ]

    def category_descriptions(self):
        return {"尴尬": "表达尴尬、认错或无奈"}

    def load_catalog(self, category):
        return {"items": list(self.items)}

    def pick_indexed_image(self, category, repeat_window, candidate_filenames=None):
        self.selected_filenames = candidate_filenames
        if candidate_filenames:
            return Path(candidate_filenames[0])
        return Path("caption.png")


class _PrimaryCandidateStore:
    def __init__(self):
        self.selected_filenames = None
        self.items = [
            {
                "id": "meme-awkward",
                "filename": "awkward.png",
                "primary_category": "尴尬",
                "primary_category_status": "ready",
                "semantic_tags": ["开心"],
                "semantic_summary": "发现自己说错话后尴尬地反问。",
                "description": "低头认错的反应",
                "emotion": "尴尬",
                "visible_text": "但是不是你自己发的吗",
                "text": "但是不是你自己发的吗",
                "text_meaning": "反问并指出前后矛盾，带有自嘲。",
                "use_cases": ["承认口误"],
                "avoid_cases": ["单纯开心"],
                "tags": ["尴尬", "开心"],
                "indexed": True,
            },
            {
                "id": "meme-happy",
                "filename": "happy.png",
                "primary_category": "开心",
                "primary_category_status": "ready",
                "semantic_tags": [],
                "semantic_summary": "轻松庆祝成功。",
                "description": "开心庆祝",
                "emotion": "开心",
                "visible_text": "太好了",
                "text": "太好了",
                "text_meaning": "表达积极确认。",
                "use_cases": ["庆祝成功"],
                "avoid_cases": [],
                "tags": ["开心"],
                "indexed": True,
            },
        ]

    def primary_category_descriptions(self):
        return {"尴尬": "表达尴尬、认错或无奈", "开心": "表达积极确认"}

    def load_primary_catalog(self, category):
        return {
            "items": [
                item for item in self.items if item["primary_category"] == category
            ]
        }

    def pick_indexed_primary_image(
        self, category, repeat_window, candidate_filenames=None
    ):
        self.selected_filenames = candidate_filenames
        if candidate_filenames:
            return Path(candidate_filenames[0])
        return Path("happy.png" if category == "开心" else "awkward.png")


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

    def test_model_selected_candidate_controls_the_indexed_image(self):
        store = _CandidateStore()
        prompts = []

        async def generate(*args, **kwargs):
            prompts.append(args[1])
            return (
                '{"should_send":true,"category":"尴尬",'
                '"candidate_id":"meme-safe","confidence":0.9,"reason":"认错"}'
            )

        service = MemeSelectionService(
            store=store,
            config=_Config(),
            generate=generate,
            event_text=lambda event: event.get_message_str(),
            image_details=lambda path: {
                "filename": path.name,
                "description": "",
                "emotion": "尴尬",
                "text": "",
            },
            model_bool=lambda value, default: bool(value)
            if value is not None
            else default,
        )

        result = asyncio.run(
            service.choose(
                FakeEvent(message_text="但是不是你自己发的吗"),
                "确实是我弄错了。",
            )
        )

        self.assertEqual(result, Path("safe.png"))
        self.assertEqual(store.selected_filenames, ["safe.png"])
        self.assertIn("meme-safe", prompts[0])
        self.assertIn("这是一段不适合当前语境的配字", prompts[0])

    def test_primary_category_routing_does_not_use_secondary_tag(self):
        store = _PrimaryCandidateStore()
        prompts = []

        async def generate(*args, **kwargs):
            prompts.append(args[1])
            return (
                '{"should_send":true,"category":"开心",'
                '"candidate_id":"meme-awkward","confidence":0.9,"reason":"庆祝"}'
            )

        service = MemeSelectionService(
            store=store,
            config=_Config(),
            generate=generate,
            event_text=lambda event: event.get_message_str(),
            image_details=lambda path: {"filename": path.name, "description": ""},
            model_bool=lambda value, default: bool(value)
            if value is not None
            else default,
        )

        result = asyncio.run(
            service.choose(FakeEvent(message_text="庆祝成功"), "太好了！")
        )

        self.assertEqual(result, Path("happy.png"))
        self.assertEqual(store.selected_filenames, None)
        self.assertIn("但是不是你自己发的吗", prompts[0])
        self.assertIn("反问并指出前后矛盾", prompts[0])
        self.assertIn("单纯开心", prompts[0])


if __name__ == "__main__":
    unittest.main()
