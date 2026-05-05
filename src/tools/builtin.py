"""Builtin tool adapter."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.tools.base import Tool, ToolDefinition


class BuiltinTool(Tool):
    def __init__(
        self,
        definition: ToolDefinition,
        handler: Callable[[dict[str, Any]], Awaitable[Any]],
    ) -> None:
        self._definition = definition
        self._handler = handler

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, arguments: dict[str, Any]) -> Any:
        return await self._handler(arguments)
