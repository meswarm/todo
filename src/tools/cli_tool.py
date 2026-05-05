"""Safe CLI tool adapter."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from string import Formatter
from typing import Any

from src.tools.base import Tool, ToolDefinition


class CLITool(Tool):
    _UNSAFE_OPERATORS = (";", "&&", "||", "|", "`", "$(")

    def __init__(
        self,
        name: str,
        description: str,
        command: str,
        parameters: dict[str, Any],
        work_dir: Path,
    ) -> None:
        self._name = name
        self._description = description
        self._command = command
        self._parameters = parameters
        self._work_dir = work_dir.resolve()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description=self._description,
            parameters={"type": "object", "properties": self._parameters, "required": []},
        )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        rendered = self._command

        for key, value in arguments.items():
            rendered = rendered.replace("{" + key + "}", shlex.quote(str(value)))

        placeholders = {
            field for _, field, _, _ in Formatter().parse(rendered) if field
        }
        if placeholders:
            raise ValueError(f"Missing argument(s) for command placeholders: {', '.join(sorted(placeholders))}")

        parts = self._validate_command(rendered)

        process = await asyncio.create_subprocess_shell(
            rendered,
            cwd=self._work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return {
            "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

    def _validate_command(self, command: str) -> list[str]:
        if not command or not command.strip():
            raise ValueError("Command is empty")

        if any(op in command for op in self._UNSAFE_OPERATORS):
            raise ValueError("Unsafe shell operator in command template")

        parts = shlex.split(command)
        if not parts:
            raise ValueError("Command is empty")

        for part in parts[1:]:
            for candidate in self._path_candidates(part):
                if self._looks_like_path(candidate):
                    if candidate.startswith("~"):
                        candidate = str(Path(candidate).expanduser())
                    resolved = (
                        (self._work_dir / candidate).resolve()
                        if not candidate.startswith(("/", "\\"))
                        else Path(candidate).resolve()
                    )
                    if not resolved.is_relative_to(self._work_dir):
                        raise ValueError(f"Command path escapes work_dir: {candidate}")
        return parts

    def _path_candidates(self, token: str) -> list[str]:
        if "=" in token:
            left, right = token.split("=", 1)
            if right:
                return [left, right]
        return [token]

    def _looks_like_path(self, token: str) -> bool:
        return (
            token.startswith(("/", "\\", "~"))
            or token.startswith(".")
            or "/" in token
            or "\\" in token
        )
