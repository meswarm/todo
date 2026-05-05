"""Application runtime for the Matrix-first todo agent."""
from __future__ import annotations

import asyncio
import logging
import signal

from src.agent import TodoAgent
from src.config import APP_CONFIG, ensure_data_dirs, validate_runtime_config
from src.matrix_client import MatrixClient
from src.media_store import R2MediaStore
from src.scheduler import start_scheduler, stop_scheduler
from src.tool_registry import ToolRegistry
from src.tools.todo_tools import build_todo_tools


logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    for noisy_logger in ("apscheduler", "httpx", "nio"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def _register_builtin_tools(registry: ToolRegistry) -> None:
    for tool in build_todo_tools():
        try:
            registry.register(tool)
        except ValueError:
            continue


def build_agent() -> TodoAgent:
    validate_runtime_config(APP_CONFIG)
    ensure_data_dirs()

    tool_registry = ToolRegistry()
    _register_builtin_tools(tool_registry)
    media_store = R2MediaStore(APP_CONFIG.r2, APP_CONFIG.media.downloads_dir)
    matrix_client = MatrixClient(
        APP_CONFIG.matrix,
        downloads_dir=APP_CONFIG.media.downloads_dir,
        download_media=False,
    )
    return TodoAgent(
        config=APP_CONFIG,
        matrix_client=matrix_client,
        media_store=media_store,
        tool_registry=tool_registry,
    )


async def run() -> None:
    """Matrix-first runtime shell (scheduler + Matrix agent)."""
    configure_logging()
    logger.info("Starting todo runtime")

    agent = build_agent()
    start_scheduler()

    loop = asyncio.get_running_loop()
    for signame in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signame, agent.request_stop)
        except NotImplementedError:
            # Windows fallback handled by KeyboardInterrupt
            pass

    try:
        await agent.run()
    finally:
        stop_scheduler()
        logger.info("Stopping todo runtime")


def main() -> None:
    asyncio.run(run())
