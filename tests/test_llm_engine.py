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


class FakeToolCallFunctionWithArgs:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class FakeToolCallWithArgs:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = FakeToolCallFunctionWithArgs(name, arguments)


class FakeToolChoiceWithArgs:
    def __init__(self, name: str, arguments: str):
        self.message = type(
            "message",
            (),
            {
                "content": "",
                "tool_calls": [FakeToolCallWithArgs("call_1", name, arguments)],
            },
        )()


class FakeMultiToolChoiceWithArgs:
    def __init__(self, calls: list[tuple[str, str, str]]):
        self.message = type(
            "message",
            (),
            {
                "content": "",
                "tool_calls": [
                    FakeToolCallWithArgs(call_id, name, arguments)
                    for call_id, name, arguments in calls
                ],
            },
        )()


class FakeSingleToolClient:
    def __init__(self, name: str, arguments: str):
        self.completions = type("completions", (), {"create": self._create})()
        self.name = name
        self.arguments = arguments
        self.calls = []

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "response",
            (),
            {"choices": [FakeToolChoiceWithArgs(self.name, self.arguments)]},
        )()


class FakeMultiToolClient:
    def __init__(self, calls: list[tuple[str, str, str]]):
        self.completions = type("completions", (), {"create": self._create})()
        self.calls_to_return = calls
        self.calls = []

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "response",
            (),
            {"choices": [FakeMultiToolChoiceWithArgs(self.calls_to_return)]},
        )()


class FakeAskThenToolClient:
    def __init__(self, tool_name: str, arguments: str):
        self.completions = type("completions", (), {"create": self._create})()
        self.tool_name = tool_name
        self.arguments = arguments
        self.calls = []

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return FakeResponse("请问是上午、下午还是晚上？")
        return type(
            "response",
            (),
            {"choices": [FakeToolChoiceWithArgs(self.tool_name, self.arguments)]},
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


class FakeSingleCreateTaskClient:
    def __init__(self):
        self.completions = type("completions", (), {"create": self._create})()
        self.calls = []

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return type("response", (), {"choices": [FakeCreateTaskChoice("call_1")]})()


class CreateTaskTableTool(Tool):
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
        return {
            "id": "26053103",
            **arguments,
            "task_markdown": (
                "| ID | 标题 | 开始时间 | 详情 |\n"
                "|---|---|---|---|\n"
                "| 26053103 | 打羽毛球 | 05-31 17:10 |  |"
            ),
        }


class CapturingTaskTool(Tool):
    def __init__(self, name: str):
        self.name = name
        self.arguments = None
        self.calls: list[dict] = []

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description="Task mutation",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, arguments: dict):
        self.arguments = arguments
        self.calls.append(arguments)
        return {
            "task_markdown": (
                "| ID | 标题 | 开始时间 | 详情 |\n"
                "|---|---|---|---|\n"
                f"| 2605310{len(self.calls)} | {arguments.get('title', '给猫打针')} | "
                f"{arguments.get('scheduled_at', '05-31 19:30')} | "
                f"{arguments.get('detail', '')} |"
            )
        }


class MessageTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delete_task",
            description="Delete task",
            parameters={
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        )

    async def execute(self, arguments: dict):
        return {"message": f"已删除任务 `{arguments['task_id']}`"}


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


def test_llm_engine_returns_code_generated_task_table_without_second_model_call():
    client = FakeSingleCreateTaskClient()
    registry = ToolRegistry()
    registry.register(CreateTaskTableTool())
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="你是一个助手",
        tool_registry=registry,
        max_history=3,
    )

    reply = asyncio.run(engine.chat("!room:example", "25分钟后打羽毛球"))

    assert reply == (
        "| ID | 标题 | 开始时间 | 详情 |\n"
        "|---|---|---|---|\n"
        "| 26053103 | 打羽毛球 | 05-31 17:10 |  |"
    )
    assert len(client.calls) == 1


def test_llm_engine_returns_tool_message_without_second_model_call():
    client = FakeSingleToolClient("delete_task", '{"task_id":"26053104"}')
    registry = ToolRegistry()
    registry.register(MessageTool())
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="你是一个助手",
        tool_registry=registry,
        max_history=3,
    )

    reply = asyncio.run(engine.chat("!room:example", "删除 26053104"))

    assert reply == "已删除任务 `26053104`"
    assert len(client.calls) == 1


def test_llm_engine_adds_original_r2_media_to_create_task_detail():
    client = FakeSingleToolClient(
        "create_task",
        '{"title":"给猫打针","scheduled_at":"2026-05-31T19:30:00"}',
    )
    registry = ToolRegistry()
    tool = CapturingTaskTool("create_task")
    registry.register(tool)
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="你是一个助手",
        tool_registry=registry,
        max_history=3,
    )

    asyncio.run(
        engine.chat(
            "!room:example",
            "今晚给这只猫打针 ![猫](r2://bucket/imgs/cat.png)",
        )
    )

    assert tool.arguments["detail"] == "![猫](r2://bucket/imgs/cat.png)"


def test_llm_engine_prepends_original_r2_media_to_update_task_detail():
    client = FakeSingleToolClient(
        "update_task",
        '{"task_id":"26053107","detail":"改到晚上七点半"}',
    )
    registry = ToolRegistry()
    tool = CapturingTaskTool("update_task")
    registry.register(tool)
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="你是一个助手",
        tool_registry=registry,
        max_history=3,
    )

    asyncio.run(
        engine.chat(
            "!room:example",
            "改 26053107 [录音](r2://bucket/audios/note.mp3)",
        )
    )

    assert tool.arguments["detail"] == (
        "[录音](r2://bucket/audios/note.mp3)\n"
        "改到晚上七点半"
    )


def test_llm_engine_executes_all_create_task_calls_before_direct_reply():
    client = FakeMultiToolClient(
        [
            (
                "call_1",
                "create_task",
                '{"title":"狂犬疫苗","scheduled_at":"2026-06-04T14:00:00","time_kind":"slot","time_slot":"afternoon"}',
            ),
            (
                "call_2",
                "create_task",
                '{"title":"狂犬疫苗","scheduled_at":"2026-06-18T14:00:00","time_kind":"slot","time_slot":"afternoon"}',
            ),
        ]
    )
    registry = ToolRegistry()
    tool = CapturingTaskTool("create_task")
    registry.register(tool)
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="你是一个助手",
        tool_registry=registry,
        max_history=3,
    )

    reply = asyncio.run(engine.chat("!room:example", "添加两个狂犬疫苗日程，都是下午"))

    assert len(tool.calls) == 2
    assert tool.calls[0]["scheduled_at"] == "2026-06-04T14:00:00"
    assert tool.calls[1]["scheduled_at"] == "2026-06-18T14:00:00"
    assert "2026-06-04T14:00:00" in reply
    assert "2026-06-18T14:00:00" in reply


def test_llm_engine_carries_media_references_across_clarification_turn():
    client = FakeAskThenToolClient(
        "create_task",
        '{"title":"狂犬疫苗","scheduled_at":"2026-06-04T14:00:00","time_kind":"slot","time_slot":"afternoon"}',
    )
    registry = ToolRegistry()
    tool = CapturingTaskTool("create_task")
    registry.register(tool)
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="你是一个助手",
        tool_registry=registry,
        max_history=3,
    )

    first_reply = asyncio.run(
        engine.chat(
            "!room:example",
            "添加两个日程 ![疫苗截图](r2://bucket/imgs/vaccine.jpg)",
        )
    )
    second_reply = asyncio.run(engine.chat("!room:example", "都是下午"))

    assert "上午、下午还是晚上" in first_reply
    assert "![疫苗截图](r2://bucket/imgs/vaccine.jpg)" in tool.arguments["detail"]
    assert "![疫苗截图](r2://bucket/imgs/vaccine.jpg)" in second_reply
