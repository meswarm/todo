"""Tool registration and dispatch."""
from __future__ import annotations

from typing import Any

from src.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def register(self, tool: Tool) -> None:
        name = tool.definition.name
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = tool

    def definitions(self) -> list[dict[str, Any]]:
        return [self._tools[name].definition.as_openai_tool() for name in self.tool_names]

    async def execute_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return await self._tools[name].execute(arguments)
