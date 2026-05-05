import asyncio

from src.tool_registry import ToolRegistry
from src.tools.base import Tool, ToolDefinition


class EchoTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="echo",
            description="Echo text",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )

    async def execute(self, arguments: dict) -> dict[str, str]:
        return {"text": arguments["text"]}


def test_registry_executes_registered_tool():
    registry = ToolRegistry()
    registry.register(EchoTool())

    async def run() -> dict[str, str]:
        return await registry.execute_tool("echo", {"text": "hello"})

    result = asyncio.run(run())

    assert result == {"text": "hello"}
    assert registry.tool_names == ["echo"]
