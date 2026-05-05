"""Tool adapters package."""
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

__all__ = ["APITool", "CLITool"]


if TYPE_CHECKING:
    from .api_tool import APITool as APITool
    from .cli_tool import CLITool as CLITool


def __getattr__(name: str):
    if name == "APITool":
        return import_module(".api_tool", __name__).APITool
    if name == "CLITool":
        return import_module(".cli_tool", __name__).CLITool
    raise AttributeError(name)
