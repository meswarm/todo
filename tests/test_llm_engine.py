"""LLM engine unit tests."""
from __future__ import annotations

import asyncio

from src.llm_engine import LLMEngine
from src.tool_registry import ToolRegistry
from src.tools.base import Tool, ToolDefinition


class FakeChoice:
    def __init__(self, content):
        self.message = type("message", (), {"content": content, "tool_calls": None})()


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeChat:
    async def create(self, **kwargs):
        return FakeResponse("收到")


class FakeCompletions:
    def __init__(self):
        self.chat = FakeChat()


class FakeClient:
    def __init__(self):
        self.completions = type("completions", (), {"create": self._create})()
        self._call_count = 0

    async def _create(self, **kwargs):
        self._call_count += 1
        self._last_payload = kwargs
        return FakeResponse("收到")


class FakeToolCallFunction:
    name = "explode"
    arguments = "{}"


class FakeToolCall:
    id = "call_1"
    function = FakeToolCallFunction()


class FakeToolChoice:
    def __init__(self):
        self.message = type(
            "message",
            (),
            {"content": "", "tool_calls": [FakeToolCall()]},
        )()


class FakeToolResponse:
    def __init__(self):
        self.choices = [FakeToolChoice()]


class FakeToolThenTextClient:
    def __init__(self):
        self.completions = type("completions", (), {"create": self._create})()
        self.calls = []

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return FakeToolResponse()
        return FakeResponse("工具失败，但我还活着")


class ExplodingTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="explode",
            description="Raise an error",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, arguments: dict):
        raise ValueError("boom")


class FakeCreateTaskFunction:
    name = "create_task"
    arguments = '{"title":"给猫洗澡","scheduled_at":"2026-04-28T20:49:00"}'


class FakeCreateTaskCall:
    def __init__(self, call_id: str):
        self.id = call_id
        self.function = FakeCreateTaskFunction()


class FakeCreateTaskChoice:
    def __init__(self, call_id: str):
        self.message = type(
            "message",
            (),
            {"content": "", "tool_calls": [FakeCreateTaskCall(call_id)]},
        )()


class FakeRepeatedCreateTaskClient:
    def __init__(self):
        self.completions = type("completions", (), {"create": self._create})()
        self.calls = []

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= 2:
            return type("response", (), {"choices": [FakeCreateTaskChoice(f"call_{len(self.calls)}")]})()
        return FakeResponse("已创建")


class CountingCreateTaskTool(Tool):
    def __init__(self):
        self.count = 0

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_task",
            description="Create task",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "scheduled_at": {"type": "string"},
                },
                "required": ["title", "scheduled_at"],
            },
        )

    async def execute(self, arguments: dict):
        self.count += 1
        return {"id": f"2604280{self.count}", **arguments}


def test_llm_engine_returns_text_response():
    client = FakeClient()
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="你是一个助手",
        tool_registry=ToolRegistry(),
        max_history=3,
    )

    reply = asyncio.run(engine.chat("!room:example", "你好"))

    assert reply == "收到"


def test_llm_engine_uses_per_message_system_prompt():
    client = FakeClient()
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="静态提示词",
        tool_registry=ToolRegistry(),
        max_history=3,
    )

    asyncio.run(
        engine.chat(
            "!room:example",
            "今天有哪些任务",
            system_prompt="动态提示词\n今天任务:\n- 开会",
        )
    )

    assert client._last_payload["messages"][0] == {
        "role": "system",
        "content": "动态提示词\n今天任务:\n- 开会",
    }


def test_llm_engine_returns_tool_errors_to_model_instead_of_crashing():
    client = FakeToolThenTextClient()
    registry = ToolRegistry()
    registry.register(ExplodingTool())
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="你是一个助手",
        tool_registry=registry,
        max_history=3,
    )

    reply = asyncio.run(engine.chat("!room:example", "触发工具"))

    assert reply == "工具失败，但我还活着"
    tool_message = next(
        message for message in client.calls[1]["messages"] if message["role"] == "tool"
    )
    assert tool_message["role"] == "tool"
    assert "boom" in tool_message["content"]


def test_llm_engine_deduplicates_repeated_mutating_tool_call_in_one_turn():
    client = FakeRepeatedCreateTaskClient()
    registry = ToolRegistry()
    tool = CountingCreateTaskTool()
    registry.register(tool)
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="你是一个助手",
        tool_registry=registry,
        max_history=3,
    )

    reply = asyncio.run(engine.chat("!room:example", "5分钟后给猫洗澡"))

    assert reply == "已创建"
    assert tool.count == 1
