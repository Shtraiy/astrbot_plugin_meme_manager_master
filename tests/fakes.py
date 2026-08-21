"""Minimal fakes and import stubs for offline behavioral tests.

Fake objects only implement what production code actually reads; accessing any
other attribute raises AttributeError instead of being swallowed by a mock.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


class _Strict:
    """Base for fakes that fail loudly on unexpected attribute access."""

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            f"{type(self).__name__} does not implement attribute {name!r}"
        )


class FakeEvent(_Strict):
    """Event fake supporting the attributes capture dispatch actually reads."""

    def __init__(
        self,
        message_text: str = "",
        umo: str = "group_test",
        session_id: str = "session-1",
        sender_id: str = "user-1",
        message_id: str = "msg-1",
    ):
        self.message_text = message_text
        self.unified_msg_origin = umo
        self.session_id = session_id
        self.sender_id = sender_id
        self.message_id = message_id
        self.message_obj = None
        self._result: FakeResult | None = None
        self._extras: dict[str, Any] = {}
        self.stopped = False
        self._messages: list[Any] = []

    def get_result(self) -> FakeResult | None:
        return self._result

    def set_result(self, result: Any) -> None:
        self._result = result

    def plain_result(self, text: str) -> FakeResult:
        from astrbot.api.message_components import Plain

        return FakeResult([Plain(text)])

    def chain_result(self, chain: list[Any]) -> FakeResult:
        return FakeResult(list(chain))

    def get_extra(self, key: str, default: Any = None) -> Any:
        return self._extras.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value

    def get_message_str(self) -> str:
        return self.message_text

    def get_message_outline(self) -> str:
        return self.message_text

    def get_messages(self) -> list[Any]:
        return self._messages

    def get_sender_id(self) -> str:
        return self.sender_id

    def stop_event(self) -> None:
        self.stopped = True


class FakeResult(_Strict):
    def __init__(self, chain: list[Any] | None = None):
        self.chain = chain if chain is not None else []


class FakeContext(_Strict):
    def __init__(self) -> None:
        self.provider_manager = types.SimpleNamespace(
            personas=[],
            llm_tools=types.SimpleNamespace(func_list=[]),
        )
        self.registered_llm_tools: list[Any] = []

    def add_llm_tools(self, *tools: Any) -> None:
        self.registered_llm_tools.extend(tools)

    def get_provider_by_id(self, provider_id: str):
        raise KeyError(provider_id)

    def get_using_provider(self, umo: str):
        raise KeyError(umo)

    async def send_message(self, umo: str, chain: Any) -> None:
        return None

    async def llm_generate(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("network disabled in offline tests")


class FakeProvider(_Strict):
    def __init__(self, provider_id: str = "fake-provider", model: str = "fake-model"):
        self.provider_id = provider_id
        self.provider_config = {"model": model, "modalities": ["chat", "image"]}

    def meta(self):
        return types.SimpleNamespace(model=self.provider_config["model"])


def install_runtime_stubs() -> None:
    """Install minimal astrbot/aiohttp modules so capture.py can be imported."""
    if "astrbot" in sys.modules:
        return

    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    components = types.ModuleType("astrbot.api.message_components")
    event_mod = types.ModuleType("astrbot.api.event")
    star = types.ModuleType("astrbot.api.star")

    class Plain:
        def __init__(self, text: str):
            self.text = text

    class Image:
        def __init__(self, path: str):
            self.path = path

        @classmethod
        def fromFileSystem(cls, path: str) -> "Image":
            return cls(path)

    class MessageChain:
        def __init__(self):
            self.message: list[Any] = []

        def file_image(self, path: str) -> "MessageChain":
            self.message.append(Image.fromFileSystem(path))
            return self

    class AstrMessageEvent:
        pass

    class Context:
        pass

    class Star:
        pass

    class _Logger:
        def debug(self, *args: Any, **kwargs: Any) -> None:
            pass

        def info(self, *args: Any, **kwargs: Any) -> None:
            pass

        def warning(self, *args: Any, **kwargs: Any) -> None:
            pass

        def error(self, *args: Any, **kwargs: Any) -> None:
            pass

    components.Plain = Plain
    components.Image = Image
    components.MessageChain = MessageChain
    event_mod.AstrMessageEvent = AstrMessageEvent
    event_mod.MessageChain = MessageChain
    star.Context = Context
    star.Star = Star
    api.logger = _Logger()
    api.message_components = components
    api.event = event_mod
    api.star = star
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.message_components"] = components
    sys.modules["astrbot.api.event"] = event_mod
    sys.modules["astrbot.api.star"] = star

    core = types.ModuleType("astrbot.core")
    agent_pkg = types.ModuleType("astrbot.core.agent")
    tool_mod = types.ModuleType("astrbot.core.agent.tool")
    run_ctx_mod = types.ModuleType("astrbot.core.agent.run_context")
    agent_ctx_mod = types.ModuleType("astrbot.core.astr_agent_context")

    from dataclasses import dataclass, field
    from typing import Generic, TypeVar

    TContext = TypeVar("TContext")

    @dataclass
    class FunctionTool(Generic[TContext]):
        name: str = ""
        description: str = ""
        parameters: dict = field(default_factory=dict)
        handler: Any = None
        handler_module_path: Any = None
        active: bool = True
        is_background_task: bool = False

        async def call(self, context: Any, **kwargs: Any) -> Any:
            raise NotImplementedError(
                "FunctionTool.call() must be implemented by subclasses."
            )

    ToolExecResult = str

    class ContextWrapper:
        def __init__(
            self,
            context: Any = None,
            event: Any = None,
            messages: list | None = None,
        ):
            self.context = context
            self.event = event
            self.messages = messages if messages is not None else []

    class AstrAgentContext:
        def __init__(self, context: Any = None, event: Any = None):
            self.context = context
            self.event = event

    tool_mod.FunctionTool = FunctionTool
    tool_mod.ToolExecResult = ToolExecResult
    run_ctx_mod.ContextWrapper = ContextWrapper
    agent_ctx_mod.AstrAgentContext = AstrAgentContext
    agent_pkg.tool = tool_mod
    agent_pkg.run_context = run_ctx_mod
    core.agent = agent_pkg
    core.astr_agent_context = agent_ctx_mod
    astrbot.core = core
    sys.modules["astrbot.core"] = core
    sys.modules["astrbot.core.agent"] = agent_pkg
    sys.modules["astrbot.core.agent.tool"] = tool_mod
    sys.modules["astrbot.core.agent.run_context"] = run_ctx_mod
    sys.modules["astrbot.core.astr_agent_context"] = agent_ctx_mod

    aiohttp = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ClientTimeout:
        def __init__(self, **kwargs: Any) -> None:
            pass

    class ClientSession:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def get(self, *args: Any, **kwargs: Any) -> Any:
            raise ClientError("network disabled in offline tests")

    aiohttp.ClientError = ClientError
    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.ClientSession = ClientSession
    sys.modules["aiohttp"] = aiohttp


def install_package_alias() -> None:
    """Make the repo importable as the plugin package for relative imports."""
    if "meme_manager_master" not in sys.modules:
        package = types.ModuleType("meme_manager_master")
        package.__path__ = [str(REPO_ROOT)]
        sys.modules["meme_manager_master"] = package
