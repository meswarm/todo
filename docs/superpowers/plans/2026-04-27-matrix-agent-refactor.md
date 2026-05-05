# Matrix Agent Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor this project from a FastAPI/Webhook todo service into a lean Matrix-first todo agent with integrated LLM, tools, R2 media storage, skills, context, scheduler, and JSON persistence.

**Architecture:** The application runs as one process started by `make run`. Matrix is the only user interaction channel, Agent coordinates Matrix messages and scheduler events, LLMEngine performs reasoning and tool calling, ToolRegistry exposes todo operations as builtin tools, and R2MediaStore handles all non-text media. FastAPI routers, webhook delivery, link YAML runtime dependency, and HTTP port configuration are removed.

**Tech Stack:** Python 3.12+, Pydantic v2, python-dotenv, APScheduler, filelock, matrix-nio, OpenAI-compatible SDK, aiohttp/aiofiles, PyYAML, aioboto3, pytest.

---

## File Structure

- Create `src/app.py`: async runtime entrypoint for loading config, initializing Agent, starting scheduler, and shutting down cleanly.
- Replace `src/main.py`: small module that calls `src.app.main()`; no FastAPI or Uvicorn.
- Modify `src/config.py`: environment-driven config model, default `db` and `downloads` paths, Matrix/LLM/R2/media/skills/prompt settings.
- Create `src/agent.py`: todo-specific Agent orchestration, message handling, scheduler notification sending, file path/R2 handling.
- Create `src/matrix_client.py`: Matrix login, sync loop, text send, media receive, no Matrix media persistence as final storage.
- Create `src/llm_engine.py`: OpenAI-compatible chat completions, history, tool call loop, optional vision input.
- Create `src/tool_registry.py`: tool registration and dispatch.
- Create `src/tools/base.py`, `src/tools/builtin.py`, `src/tools/api_tool.py`, `src/tools/cli_tool.py`: generic tool interfaces and implementations.
- Create `src/tools/todo_tools.py`: builtin todo tool definitions backed by local services.
- Create `src/media_store.py`: R2 upload/download/cache abstraction and category download paths.
- Create `src/skills.py`: load `SKILL.md` files and format them for prompt injection.
- Create `src/context.py`: dynamic context hooks for date, agenda, overdue tasks, and stats.
- Create `src/services/notification.py`: in-process notification sink used by scheduler jobs.
- Modify `src/scheduler/*.py`: remove webhook calls and send events through `notification.py`.
- Keep `src/services/task_service.py`, `src/services/agenda_service.py`, `src/storage/json_store.py`, `src/models/*`, `src/utils/*`: reuse business logic and persistence.
- Delete or orphan from runtime `src/routers/*` and `src/services/webhook.py`: not imported by the app after the refactor.
- Create `prompts/system_prompt.md`: primary system prompt.
- Modify `.env.example`: remove API/Webhook variables; add Matrix, LLM, R2, media, prompt, skills, db, downloads settings.
- Modify `requirements.txt`: remove FastAPI/Uvicorn/httpx if unused; add Matrix/LLM/R2/skills dependencies.
- Modify `Makefile`: `make run` starts the Matrix agent; no API server.
- Modify `README.md` and `README_EN.md`: describe Matrix agent usage, `.env`, R2, downloads, and make commands.
- Modify tests and add focused tests under `tests/`: config, tools, notification sink, scheduler behavior, media path classification, prompt loading.

---

## Task 1: Establish Runtime Configuration

**Files:**
- Modify: `src/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add failing config tests**

Create or replace focused assertions in `tests/test_config.py`:

```python
from pathlib import Path

from src.config import AppConfig, parse_bool


def test_parse_bool_accepts_common_true_values():
    assert parse_bool("1") is True
    assert parse_bool("true") is True
    assert parse_bool("yes") is True
    assert parse_bool("on") is True


def test_parse_bool_accepts_common_false_values():
    assert parse_bool("0") is False
    assert parse_bool("false") is False
    assert parse_bool("no") is False
    assert parse_bool("off") is False
    assert parse_bool("") is False


def test_app_config_defaults_to_db_and_downloads(monkeypatch, tmp_path):
    monkeypatch.setenv("TODO_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("MATRIX_HOMESERVER", "https://matrix.example")
    monkeypatch.setenv("MATRIX_USER", "@todo:example")
    monkeypatch.setenv("MATRIX_PASSWORD", "secret")
    monkeypatch.setenv("MATRIX_ROOMS", "!room:example,!ops:example")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "llm-secret")
    monkeypatch.setenv("LLM_MODEL", "qwen-plus")

    config = AppConfig.from_env()

    assert config.data_dir == tmp_path / "db"
    assert config.downloads_dir == tmp_path / "downloads"
    assert config.download_imgs_dir == tmp_path / "downloads" / "imgs"
    assert config.matrix.rooms == ["!room:example", "!ops:example"]
    assert config.llm.vision_enabled is False
```

- [ ] **Step 2: Run the failing test**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_config.py -v`

Expected: FAIL because `AppConfig` and `parse_bool` do not exist yet.

- [ ] **Step 3: Implement config model**

Replace module-level API/Webhook config in `src/config.py` with an environment-backed model while keeping compatibility constants for existing storage and scheduler modules during the transition:

```python
"""Application configuration loaded from .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(os.getenv("TODO_BASE_DIR", Path(__file__).resolve().parent.parent))

load_dotenv(BASE_DIR / ".env.example")
load_dotenv(BASE_DIR / ".env", override=True)


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}，请检查项目根目录 .env")
    return value


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


@dataclass(frozen=True)
class MatrixConfig:
    homeserver: str
    user: str
    password: str
    rooms: list[str]


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_history: int
    enable_thinking: bool
    vision_enabled: bool


@dataclass(frozen=True)
class R2Config:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    public_url: str

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.access_key and self.secret_key and self.bucket)


@dataclass(frozen=True)
class MediaConfig:
    downloads_dir: Path
    download_images: bool
    download_videos: bool
    download_audios: bool
    download_files: bool


@dataclass(frozen=True)
class AppConfig:
    base_dir: Path
    data_dir: Path
    docs_dir: Path
    files_dir: Path
    stats_dir: Path
    downloads_dir: Path
    prompt_path: Path
    skills_dir: Path | None
    matrix: MatrixConfig
    llm: LLMConfig
    r2: R2Config
    media: MediaConfig
    morning_hour: int
    morning_minute: int
    evening_hour: int
    evening_minute: int

    @property
    def download_imgs_dir(self) -> Path:
        return self.downloads_dir / "imgs"

    @classmethod
    def from_env(cls) -> "AppConfig":
        base_dir = Path(os.getenv("TODO_BASE_DIR", str(BASE_DIR))).expanduser()
        data_dir = Path(os.getenv("TODO_DATA_DIR", str(base_dir / "db"))).expanduser()
        downloads_dir = Path(os.getenv("TODO_DOWNLOADS_DIR", str(base_dir / "downloads"))).expanduser()
        skills_raw = os.getenv("TODO_SKILLS_DIR", "").strip()
        return cls(
            base_dir=base_dir,
            data_dir=data_dir,
            docs_dir=data_dir / "docs",
            files_dir=data_dir / "files",
            stats_dir=data_dir / "stats",
            downloads_dir=downloads_dir,
            prompt_path=Path(os.getenv("TODO_SYSTEM_PROMPT", str(base_dir / "prompts" / "system_prompt.md"))).expanduser(),
            skills_dir=Path(skills_raw).expanduser() if skills_raw else None,
            matrix=MatrixConfig(
                homeserver=_required_env("MATRIX_HOMESERVER"),
                user=_required_env("MATRIX_USER"),
                password=_required_env("MATRIX_PASSWORD"),
                rooms=_csv_env("MATRIX_ROOMS"),
            ),
            llm=LLMConfig(
                base_url=_required_env("LLM_BASE_URL"),
                api_key=_required_env("LLM_API_KEY"),
                model=_required_env("LLM_MODEL"),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
                max_history=int(os.getenv("LLM_MAX_HISTORY", "20")),
                enable_thinking=parse_bool(os.getenv("LLM_ENABLE_THINKING")),
                vision_enabled=parse_bool(os.getenv("LLM_VISION_ENABLED")),
            ),
            r2=R2Config(
                endpoint=os.getenv("R2_ENDPOINT", ""),
                access_key=os.getenv("R2_ACCESS_KEY", ""),
                secret_key=os.getenv("R2_SECRET_KEY", ""),
                bucket=os.getenv("R2_BUCKET", "todo-media"),
                public_url=os.getenv("R2_PUBLIC_URL", ""),
            ),
            media=MediaConfig(
                downloads_dir=downloads_dir,
                download_images=parse_bool(os.getenv("R2_DOWNLOAD_IMAGES"), True),
                download_videos=parse_bool(os.getenv("R2_DOWNLOAD_VIDEOS"), True),
                download_audios=parse_bool(os.getenv("R2_DOWNLOAD_AUDIOS"), True),
                download_files=parse_bool(os.getenv("R2_DOWNLOAD_FILES"), True),
            ),
            morning_hour=int(os.getenv("TODO_MORNING_HOUR", "8")),
            morning_minute=int(os.getenv("TODO_MORNING_MINUTE", "0")),
            evening_hour=int(os.getenv("TODO_EVENING_HOUR", "21")),
            evening_minute=int(os.getenv("TODO_EVENING_MINUTE", "0")),
        )


APP_CONFIG = AppConfig.from_env()

DATA_DIR = APP_CONFIG.data_dir
TASKS_FILE = DATA_DIR / "tasks.json"
HISTORY_FILE = DATA_DIR / "history.json"
RECURRENCES_FILE = DATA_DIR / "recurrences.json"
DOCS_DIR = APP_CONFIG.docs_dir
FILES_DIR = APP_CONFIG.files_dir
STATS_DIR = APP_CONFIG.stats_dir
MORNING_PUSH_HOUR = APP_CONFIG.morning_hour
MORNING_PUSH_MINUTE = APP_CONFIG.morning_minute
EVENING_PUSH_HOUR = APP_CONFIG.evening_hour
EVENING_PUSH_MINUTE = APP_CONFIG.evening_minute


def ensure_data_dirs() -> None:
    for directory in [
        DATA_DIR,
        DOCS_DIR,
        FILES_DIR,
        STATS_DIR,
        STATS_DIR / "weekly",
        STATS_DIR / "monthly",
        APP_CONFIG.downloads_dir / "imgs",
        APP_CONFIG.downloads_dir / "videos",
        APP_CONFIG.downloads_dir / "audios",
        APP_CONFIG.downloads_dir / "files",
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    for file_path in [TASKS_FILE, HISTORY_FILE, RECURRENCES_FILE]:
        if not file_path.exists():
            file_path.write_text("[]", encoding="utf-8")
```

- [ ] **Step 4: Update `.env.example`**

Use these keys and remove host/port/webhook keys:

```dotenv
# --- Paths ---
TODO_BASE_DIR=.
TODO_DATA_DIR=./db
TODO_DOWNLOADS_DIR=./downloads
TODO_SYSTEM_PROMPT=./prompts/system_prompt.md
TODO_SKILLS_DIR=

# --- Matrix ---
MATRIX_HOMESERVER=https://matrix.example.com
MATRIX_USER=@todo-bot:example.com
MATRIX_PASSWORD=change-me
MATRIX_ROOMS=!room-id:example.com

# --- LLM ---
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=change-me
LLM_MODEL=qwen-plus
LLM_TEMPERATURE=0.7
LLM_MAX_HISTORY=20
LLM_ENABLE_THINKING=false
LLM_VISION_ENABLED=false

# --- R2 ---
R2_ENDPOINT=
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_BUCKET=todo-media
R2_PUBLIC_URL=
R2_DOWNLOAD_IMAGES=true
R2_DOWNLOAD_VIDEOS=true
R2_DOWNLOAD_AUDIOS=true
R2_DOWNLOAD_FILES=true

# --- Scheduler ---
TODO_MORNING_HOUR=8
TODO_MORNING_MINUTE=0
TODO_EVENING_HOUR=21
TODO_EVENING_MINUTE=0
```

- [ ] **Step 5: Verify config tests pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/config.py .env.example tests/test_config.py
git commit -m "refactor: centralize matrix agent configuration"
```

---

## Task 2: Remove FastAPI and Webhook Runtime Paths

**Files:**
- Modify: `src/main.py`
- Create: `src/app.py`
- Delete from runtime imports: `src/services/webhook.py`
- Modify: `requirements.txt`
- Modify: `Makefile`
- Test: `tests/test_runtime_imports.py`

- [ ] **Step 1: Add failing runtime import test**

Create `tests/test_runtime_imports.py`:

```python
import inspect

import src.main


def test_main_does_not_import_fastapi_or_uvicorn():
    source = inspect.getsource(src.main)
    assert "FastAPI" not in source
    assert "uvicorn" not in source


def test_main_exposes_agent_entrypoint():
    assert hasattr(src.main, "main")
```

- [ ] **Step 2: Run the failing test**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_runtime_imports.py -v`

Expected: FAIL because `src.main` still imports FastAPI/Uvicorn.

- [ ] **Step 3: Create async runtime shell**

Create `src/app.py`:

```python
"""Application runtime for the Matrix-first todo agent."""
from __future__ import annotations

import asyncio
import logging

from src.config import APP_CONFIG, ensure_data_dirs
from src.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


async def run() -> None:
    ensure_data_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger.info("Starting todo Matrix agent")
    logger.info("Data dir: %s", APP_CONFIG.data_dir)
    logger.info("Downloads dir: %s", APP_CONFIG.downloads_dir)
    logger.info("Matrix homeserver: %s", APP_CONFIG.matrix.homeserver)
    logger.info("Matrix rooms: %s", APP_CONFIG.matrix.rooms)
    start_scheduler()
    try:
        # Agent startup is added in Task 7.
        await asyncio.Event().wait()
    finally:
        stop_scheduler()


def main() -> None:
    asyncio.run(run())
```

- [ ] **Step 4: Replace `src/main.py`**

Use this content:

```python
"""Command entrypoint."""
from src.app import main


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Update dependencies**

In `requirements.txt`, remove FastAPI/Uvicorn/httpx and include the runtime dependencies:

```text
python-dotenv==1.0.1
pydantic==2.10.0
apscheduler==3.10.4
filelock==3.16.0
matrix-nio==0.25.2
openai==1.76.0
aiohttp==3.11.18
aiofiles==24.1.0
pyyaml==6.0.2
aioboto3==14.1.0
pytest==8.3.5
```

- [ ] **Step 6: Update Makefile**

Keep make commands minimal:

```makefile
.DEFAULT_GOAL := help

VENV_PYTHON := .venv/bin/python
VENV_PIP := .venv/bin/pip

.PHONY: help init check-venv run test clean

help:
	@echo "Available targets:"
	@echo "  make init   - Create .venv and install dependencies"
	@echo "  make run    - Start the Matrix todo agent"
	@echo "  make test   - Run the test suite"
	@echo "  make clean  - Remove Python cache files"

init:
	python3 -m venv .venv
	$(VENV_PIP) install -r requirements.txt

check-venv:
	@if [ ! -x "$(VENV_PYTHON)" ]; then \
		echo "Virtualenv not initialized. Run: make init"; \
		exit 1; \
	fi

run: check-venv
	PYTHONPATH=. $(VENV_PYTHON) -m src.main

test: check-venv
	PYTHONPATH=. $(VENV_PYTHON) -m pytest tests/ -v

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf .pytest_cache 2>/dev/null || true
```

- [ ] **Step 7: Verify runtime import test passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_runtime_imports.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/app.py src/main.py requirements.txt Makefile tests/test_runtime_imports.py
git commit -m "refactor: replace api server with agent runtime"
```

---

## Task 3: Add In-Process Scheduler Notifications

**Files:**
- Create: `src/services/notification.py`
- Modify: `src/scheduler/morning_push.py`
- Modify: `src/scheduler/evening_push.py`
- Modify: `src/scheduler/reminder_scan.py`
- Test: `tests/test_notification.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: Add notification sink tests**

Create `tests/test_notification.py`:

```python
from src.services.notification import NotificationSink, get_notification_sink


def test_notification_sink_stores_events():
    sink = NotificationSink()

    sink.publish({"type": "task_reminder", "message": "demo"})

    assert sink.drain() == [{"type": "task_reminder", "message": "demo"}]
    assert sink.drain() == []


def test_global_notification_sink_is_singleton():
    assert get_notification_sink() is get_notification_sink()
```

- [ ] **Step 2: Run the failing test**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_notification.py -v`

Expected: FAIL because `src.services.notification` does not exist.

- [ ] **Step 3: Implement notification sink**

Create `src/services/notification.py`:

```python
"""In-process notification channel from scheduler jobs to Agent."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class NotificationSink:
    _items: deque[dict[str, Any]] = field(default_factory=deque)
    _lock: Lock = field(default_factory=Lock)

    def publish(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(payload)

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._items)
            self._items.clear()
            return items


_SINK = NotificationSink()


def get_notification_sink() -> NotificationSink:
    return _SINK


def publish_notification(payload: dict[str, Any]) -> None:
    _SINK.publish(payload)
```

- [ ] **Step 4: Replace scheduler webhook calls**

In scheduler modules, replace:

```python
from src.services.webhook import push_webhook_sync
```

with:

```python
from src.services.notification import publish_notification
```

Replace calls like:

```python
push_webhook_sync(payload)
```

with:

```python
publish_notification(payload)
```

- [ ] **Step 5: Update scheduler tests**

In `tests/test_scheduler.py`, patch `publish_notification` instead of `push_webhook_sync`. Example:

```python
monkeypatch.setattr(
    "src.scheduler.reminder_scan.publish_notification",
    lambda payload: sent_payloads.append(payload),
)
```

- [ ] **Step 6: Verify notification and scheduler tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_notification.py tests/test_scheduler.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/services/notification.py src/scheduler tests/test_notification.py tests/test_scheduler.py
git commit -m "refactor: route scheduler notifications in process"
```

---

## Task 4: Add Tool Registry and Todo Builtin Tools

**Files:**
- Create: `src/tools/base.py`
- Create: `src/tools/builtin.py`
- Create: `src/tool_registry.py`
- Create: `src/tools/todo_tools.py`
- Test: `tests/test_tool_registry.py`
- Test: `tests/test_todo_tools.py`

- [ ] **Step 1: Add registry tests**

Create `tests/test_tool_registry.py`:

```python
import pytest

from src.tool_registry import ToolRegistry
from src.tools.base import Tool, ToolDefinition


class EchoTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            name="echo",
            description="Echo text",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )

    async def execute(self, arguments):
        return {"text": arguments["text"]}


@pytest.mark.asyncio
async def test_registry_executes_registered_tool():
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = await registry.execute_tool("echo", {"text": "hello"})

    assert result == {"text": "hello"}
    assert registry.tool_names == ["echo"]
```

- [ ] **Step 2: Run the failing registry test**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_tool_registry.py -v`

Expected: FAIL because tool modules do not exist.

- [ ] **Step 3: Implement base tool and registry**

Create `src/tools/base.py`:

```python
"""Tool interfaces for LLM function calling."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Tool(ABC):
    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> Any:
        raise NotImplementedError
```

Create `src/tool_registry.py`:

```python
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
```

- [ ] **Step 4: Add minimal builtin wrapper**

Create `src/tools/builtin.py`:

```python
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
```

- [ ] **Step 5: Add todo tool tests**

Create `tests/test_todo_tools.py` with a smoke test that registry exposes core todo operations:

```python
from src.tools.todo_tools import build_todo_tools


def test_build_todo_tools_exposes_core_operations():
    names = sorted(tool.definition.name for tool in build_todo_tools())

    assert "create_task" in names
    assert "list_tasks" in names
    assert "update_task_status" in names
    assert "get_agenda" in names
    assert "search_tasks" in names
```

- [ ] **Step 6: Implement todo tool definitions**

Create `src/tools/todo_tools.py`:

```python
"""Todo builtin tools exposed to the LLM."""
from __future__ import annotations

from typing import Any

from src.models.task import TaskCreate, TaskStatus
from src.services.agenda_service import get_agenda
from src.services.task_service import TaskService
from src.tools.base import ToolDefinition
from src.tools.builtin import BuiltinTool


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def build_todo_tools() -> list[BuiltinTool]:
    service = TaskService()

    async def create_task(args: dict[str, Any]) -> dict[str, Any]:
        task = service.create_task(TaskCreate(**args))
        return task.model_dump(mode="json")

    async def list_tasks(args: dict[str, Any]) -> list[dict[str, Any]]:
        status = args.get("status")
        tasks = service.list_tasks(status=TaskStatus(status) if status else None)
        return [task.model_dump(mode="json") for task in tasks]

    async def update_task_status(args: dict[str, Any]) -> dict[str, Any]:
        task = service.update_status(args["task_id"], TaskStatus(args["status"]))
        return task.model_dump(mode="json")

    async def agenda(args: dict[str, Any]) -> dict[str, Any]:
        return get_agenda().model_dump(mode="json")

    async def search_tasks(args: dict[str, Any]) -> list[dict[str, Any]]:
        tasks = service.search(args["query"])
        return [task.model_dump(mode="json") for task in tasks]

    return [
        BuiltinTool(
            ToolDefinition(
                name="create_task",
                description="Create a todo task.",
                parameters=_schema(
                    {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "deadline": {"type": "string"},
                    },
                    ["title"],
                ),
            ),
            create_task,
        ),
        BuiltinTool(
            ToolDefinition(
                name="list_tasks",
                description="List todo tasks, optionally filtered by status.",
                parameters=_schema(
                    {"status": {"type": "string", "enum": ["pending", "in_progress", "completed", "abandoned"]}},
                    [],
                ),
            ),
            list_tasks,
        ),
        BuiltinTool(
            ToolDefinition(
                name="update_task_status",
                description="Update a task status.",
                parameters=_schema(
                    {
                        "task_id": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "abandoned"]},
                    },
                    ["task_id", "status"],
                ),
            ),
            update_task_status,
        ),
        BuiltinTool(
            ToolDefinition(name="get_agenda", description="Get current agenda.", parameters=_schema({}, [])),
            agenda,
        ),
        BuiltinTool(
            ToolDefinition(
                name="search_tasks",
                description="Search tasks by keyword.",
                parameters=_schema({"query": {"type": "string"}}, ["query"]),
            ),
            search_tasks,
        ),
    ]
```

- [ ] **Step 7: Verify tool tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_tool_registry.py tests/test_todo_tools.py -v`

Expected: PASS. If `TaskService` method names differ, adapt `todo_tools.py` to the existing service API and keep the test expectations unchanged.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/tools src/tool_registry.py tests/test_tool_registry.py tests/test_todo_tools.py
git commit -m "feat: expose todo operations as builtin tools"
```

---

## Task 5: Add API and CLI Tool Adapters

**Files:**
- Create: `src/tools/api_tool.py`
- Create: `src/tools/cli_tool.py`
- Test: `tests/test_api_cli_tools.py`

- [ ] **Step 1: Add adapter tests**

Create `tests/test_api_cli_tools.py`:

```python
import pytest

from src.tools.api_tool import APITool
from src.tools.cli_tool import CLITool


class FakeResponse:
    status_code = 200

    def json(self):
        return {"ok": True}

    @property
    def text(self):
        return "ok"


class FakeHTTPClient:
    def __init__(self):
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeResponse()


@pytest.mark.asyncio
async def test_api_tool_renders_path_params():
    client = FakeHTTPClient()
    tool = APITool(
        name="get_item",
        description="Get item",
        endpoint="https://api.example/items/{item_id}",
        method="GET",
        parameters={"item_id": {"type": "string"}},
        client=client,
    )

    result = await tool.execute({"item_id": "abc"})

    assert result == {"ok": True}
    assert client.calls[0][1] == "https://api.example/items/abc"


@pytest.mark.asyncio
async def test_cli_tool_rejects_command_outside_work_dir(tmp_path):
    tool = CLITool(
        name="bad",
        description="Bad command",
        command="cat /etc/passwd",
        parameters={},
        work_dir=tmp_path,
    )

    with pytest.raises(ValueError):
        await tool.execute({})
```

- [ ] **Step 2: Run the failing adapter tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_api_cli_tools.py -v`

Expected: FAIL because API and CLI adapters do not exist.

- [ ] **Step 3: Implement `APITool`**

Create `src/tools/api_tool.py`:

```python
"""REST API tool adapter."""
from __future__ import annotations

from typing import Any

import aiohttp

from src.tools.base import Tool, ToolDefinition


class APITool(Tool):
    def __init__(
        self,
        name: str,
        description: str,
        endpoint: str,
        method: str,
        parameters: dict[str, Any],
        headers: dict[str, str] | None = None,
        client: Any | None = None,
    ) -> None:
        self._name = name
        self._description = description
        self._endpoint = endpoint
        self._method = method.upper()
        self._parameters = parameters
        self._headers = headers or {}
        self._client = client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description=self._description,
            parameters={"type": "object", "properties": self._parameters, "required": []},
        )

    async def execute(self, arguments: dict[str, Any]) -> Any:
        url = self._endpoint
        query: dict[str, Any] = {}
        for key, value in arguments.items():
            token = "{" + key + "}"
            if token in url:
                url = url.replace(token, str(value))
            else:
                query[key] = value

        if self._client is not None:
            response = await self._client.request(self._method, url, params=query, headers=self._headers)
            return response.json()

        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.request(self._method, url, params=query if self._method == "GET" else None, json=query if self._method != "GET" else None) as response:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    return await response.json()
                return await response.text()
```

- [ ] **Step 4: Implement `CLITool`**

Create `src/tools/cli_tool.py`:

```python
"""Safe CLI tool adapter."""
from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Any

from src.tools.base import Tool, ToolDefinition


class CLITool(Tool):
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
        self._validate_command(rendered)
        proc = await asyncio.create_subprocess_shell(
            rendered,
            cwd=self._work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

    def _validate_command(self, command: str) -> None:
        parts = shlex.split(command)
        for part in parts[1:]:
            if part.startswith("/"):
                path = Path(part).resolve()
                if not path.is_relative_to(self._work_dir):
                    raise ValueError(f"CLI path outside work_dir: {path}")
```

- [ ] **Step 5: Verify adapter tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_api_cli_tools.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/tools/api_tool.py src/tools/cli_tool.py tests/test_api_cli_tools.py
git commit -m "feat: add api and cli tool adapters"
```

---

## Task 6: Add Prompt, Skills, Context, and LLM Engine

**Files:**
- Create: `prompts/system_prompt.md`
- Create: `src/skills.py`
- Create: `src/context.py`
- Create: `src/llm_engine.py`
- Test: `tests/test_prompt_context.py`
- Test: `tests/test_llm_engine.py`

- [ ] **Step 1: Add prompt/context tests**

Create `tests/test_prompt_context.py`:

```python
from pathlib import Path

from src.context import build_context_prompt
from src.skills import load_system_prompt


def test_load_system_prompt_reads_markdown(tmp_path):
    path = tmp_path / "system_prompt.md"
    path.write_text("你是 todo agent。", encoding="utf-8")

    assert load_system_prompt(path) == "你是 todo agent。"


def test_build_context_prompt_contains_sections():
    prompt = build_context_prompt({"today": "2026-04-27", "agenda": "无任务"})

    assert "today" in prompt
    assert "2026-04-27" in prompt
    assert "agenda" in prompt
```

- [ ] **Step 2: Implement prompt and context helpers**

Create `prompts/system_prompt.md`:

```markdown
你是一个通过 Matrix 与用户交互的个人待办 Agent。

你的职责：
- 帮用户创建、查询、更新和复盘任务。
- 遇到明确的任务管理需求时优先调用工具，不要只用自然语言承诺。
- 对时间、截止日期、提醒和重复规则保持严谨。
- 如果用户发送图片、音频、视频或文件，先说明你能识别到的媒体信息，再根据可用工具处理。
- 回复应简洁、可执行，避免输出内部工具调用细节。
```

Create `src/skills.py`:

```python
"""Prompt and skill loading."""
from __future__ import annotations

from pathlib import Path


def load_system_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"System prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()
```

Create `src/context.py`:

```python
"""Dynamic context formatting for LLM prompts."""
from __future__ import annotations

from typing import Any


def build_context_prompt(values: dict[str, Any]) -> str:
    if not values:
        return ""
    lines = ["\n\n# Dynamic Context"]
    for key, value in values.items():
        lines.append(f"\n## {key}\n{value}")
    return "\n".join(lines)
```

- [ ] **Step 3: Add LLM engine tests with fake client**

Create `tests/test_llm_engine.py`:

```python
import pytest

from src.llm_engine import LLMEngine
from src.tool_registry import ToolRegistry


class FakeChoice:
    def __init__(self, content):
        self.message = type("Message", (), {"content": content, "tool_calls": None})()


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    async def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeResponse("收到")


class FakeClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": FakeCompletions()})()


@pytest.mark.asyncio
async def test_llm_engine_returns_text_response():
    client = FakeClient()
    engine = LLMEngine(
        client=client,
        model="demo",
        system_prompt="system",
        tool_registry=ToolRegistry(),
        max_history=3,
        vision_enabled=False,
    )

    reply = await engine.chat("!room:example", "你好")

    assert reply == "收到"
```

- [ ] **Step 4: Implement minimal LLM engine**

Create `src/llm_engine.py`:

```python
"""OpenAI-compatible LLM engine with tool calling support."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from openai import AsyncOpenAI

from src.tool_registry import ToolRegistry

MAX_TOOL_CALL_ROUNDS = 10


class LLMEngine:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        system_prompt: str,
        tool_registry: ToolRegistry,
        max_history: int,
        vision_enabled: bool,
        temperature: float = 0.7,
    ) -> None:
        self._client = client
        self._model = model
        self._system_prompt = system_prompt
        self._tool_registry = tool_registry
        self._max_history = max_history
        self._vision_enabled = vision_enabled
        self._temperature = temperature
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)

    async def chat(self, room_id: str, user_message: str) -> str:
        history = self._history[room_id][-self._max_history :]
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        response = await self._complete(messages)
        message = response.choices[0].message

        rounds = 0
        while getattr(message, "tool_calls", None) and rounds < MAX_TOOL_CALL_ROUNDS:
            rounds += 1
            messages.append(message)
            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                result = await self._tool_registry.execute_tool(call.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
            response = await self._complete(messages)
            message = response.choices[0].message

        content = message.content or ""
        self._history[room_id].extend(
            [{"role": "user", "content": user_message}, {"role": "assistant", "content": content}]
        )
        self._history[room_id] = self._history[room_id][-self._max_history :]
        return content

    async def _complete(self, messages: list[dict[str, Any]]) -> Any:
        return await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=self._tool_registry.definitions(),
            temperature=self._temperature,
        )
```

- [ ] **Step 5: Verify prompt and LLM tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_prompt_context.py tests/test_llm_engine.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add prompts/system_prompt.md src/skills.py src/context.py src/llm_engine.py tests/test_prompt_context.py tests/test_llm_engine.py
git commit -m "feat: add prompt context and llm engine"
```

---

## Task 7: Add R2 Media Store and Download Classification

**Files:**
- Create: `src/media_store.py`
- Test: `tests/test_media_store.py`

- [ ] **Step 1: Add media classification tests**

Create `tests/test_media_store.py`:

```python
from pathlib import Path

from src.media_store import category_for_mime, local_download_path


def test_category_for_mime():
    assert category_for_mime("image/png") == "imgs"
    assert category_for_mime("video/mp4") == "videos"
    assert category_for_mime("audio/mpeg") == "audios"
    assert category_for_mime("application/pdf") == "files"


def test_local_download_path_uses_category(tmp_path):
    path = local_download_path(tmp_path, "image/png", "demo.png")

    assert path == tmp_path / "imgs" / "demo.png"
```

- [ ] **Step 2: Run the failing test**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_media_store.py -v`

Expected: FAIL because `src.media_store` does not exist.

- [ ] **Step 3: Implement media classification and R2 shell**

Create `src/media_store.py`:

```python
"""R2 media storage and local download layout."""
from __future__ import annotations

from pathlib import Path

from src.config import R2Config


def category_for_mime(mime: str) -> str:
    if mime.startswith("image/"):
        return "imgs"
    if mime.startswith("video/"):
        return "videos"
    if mime.startswith("audio/"):
        return "audios"
    return "files"


def local_download_path(downloads_dir: Path, mime: str, filename: str) -> Path:
    return downloads_dir / category_for_mime(mime) / filename


class R2MediaStore:
    def __init__(self, config: R2Config, downloads_dir: Path) -> None:
        self._config = config
        self._downloads_dir = downloads_dir

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    async def upload(self, path: Path, room_prefix: str, mime: str) -> str:
        if not self.enabled:
            raise RuntimeError("R2 is not configured")
        # Full aioboto3 upload implementation is migrated from link/media_store.py.
        key = f"{room_prefix.strip('/')}/{category_for_mime(mime)}/{path.name}"
        return f"r2://{self._config.bucket}/{key}"

    async def download_to_local(self, filename: str, mime: str, content: bytes) -> Path:
        path = local_download_path(self._downloads_dir, mime, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path
```

- [ ] **Step 4: Migrate complete R2 behavior**

Port the production upload/download logic from `/home/txl/Code/meswarm/link/link/media_store.py` into `src/media_store.py`. Preserve this local layout rule:

```text
downloads/imgs
downloads/videos
downloads/audios
downloads/files
```

Preserve this storage rule:

```text
Only non-text media is stored through R2. Matrix media repository is not the durable storage layer.
```

- [ ] **Step 5: Verify media tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_media_store.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/media_store.py tests/test_media_store.py
git commit -m "feat: add r2 media store layout"
```

---

## Task 8: Add Matrix Client and Agent Orchestration

**Files:**
- Create: `src/matrix_client.py`
- Create: `src/agent.py`
- Modify: `src/app.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Add Agent test with fakes**

Create `tests/test_agent.py`:

```python
import pytest

from src.agent import Agent


class FakeMatrix:
    def __init__(self):
        self.sent = []
        self.callback = None

    def on_message(self, callback):
        self.callback = callback

    async def send_text(self, room_id, text):
        self.sent.append((room_id, text))

    async def set_typing(self, room_id, enabled):
        pass


class FakeLLM:
    async def chat(self, room_id, content):
        return f"reply:{content}"


@pytest.mark.asyncio
async def test_agent_replies_to_matrix_message():
    matrix = FakeMatrix()
    agent = Agent(matrix_client=matrix, llm_engine=FakeLLM(), notification_sink=None, media_store=None)

    await agent.handle_user_message("!room:example", "@u:example", "hello")

    assert matrix.sent == [("!room:example", "reply:hello")]
```

- [ ] **Step 2: Implement Agent orchestration**

Create `src/agent.py`:

```python
"""Todo Agent orchestration."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Agent:
    def __init__(
        self,
        matrix_client: Any,
        llm_engine: Any,
        notification_sink: Any,
        media_store: Any,
    ) -> None:
        self._matrix_client = matrix_client
        self._llm_engine = llm_engine
        self._notification_sink = notification_sink
        self._media_store = media_store
        self._matrix_client.on_message(self.handle_user_message)

    async def handle_user_message(self, room_id: str, sender: str, content: str) -> None:
        logger.info("Processing Matrix message room=%s sender=%s", room_id, sender)
        await self._matrix_client.set_typing(room_id, True)
        try:
            reply = await self._llm_engine.chat(room_id, content)
            if reply.strip():
                await self._matrix_client.send_text(room_id, reply)
        finally:
            await self._matrix_client.set_typing(room_id, False)

    async def flush_notifications(self) -> None:
        if self._notification_sink is None:
            return
        for payload in self._notification_sink.drain():
            text = payload.get("message") or str(payload)
            for room_id in self._matrix_client.rooms:
                await self._matrix_client.send_text(room_id, text)
```

- [ ] **Step 3: Implement Matrix client by migrating link code**

Create `src/matrix_client.py` by adapting `/home/txl/Code/meswarm/link/link/matrix_client.py` with these required differences:

```text
- Constructor accepts MatrixConfig and downloads_dir-related settings from AppConfig.
- Text messages call Agent callback directly.
- Media messages are converted into local file/R2 descriptors for Agent.
- Durable media storage is R2, not Matrix media repository.
- Sending replies uses room_send text events only unless R2 link text is included.
```

- [ ] **Step 4: Wire runtime in `src/app.py`**

Replace the placeholder event wait with initialization:

```python
from openai import AsyncOpenAI

from src.agent import Agent
from src.llm_engine import LLMEngine
from src.matrix_client import MatrixClient
from src.media_store import R2MediaStore
from src.services.notification import get_notification_sink
from src.skills import load_system_prompt
from src.tool_registry import ToolRegistry
from src.tools.todo_tools import build_todo_tools
```

Inside `run()`:

```python
registry = ToolRegistry()
for tool in build_todo_tools():
    registry.register(tool)

system_prompt = load_system_prompt(APP_CONFIG.prompt_path)
llm = LLMEngine(
    client=AsyncOpenAI(base_url=APP_CONFIG.llm.base_url, api_key=APP_CONFIG.llm.api_key),
    model=APP_CONFIG.llm.model,
    system_prompt=system_prompt,
    tool_registry=registry,
    max_history=APP_CONFIG.llm.max_history,
    vision_enabled=APP_CONFIG.llm.vision_enabled,
    temperature=APP_CONFIG.llm.temperature,
)
matrix = MatrixClient(APP_CONFIG.matrix)
media_store = R2MediaStore(APP_CONFIG.r2, APP_CONFIG.downloads_dir)
agent = Agent(matrix, llm, get_notification_sink(), media_store)
logger.info("Registered tools: %s", registry.tool_names)
await matrix.login()
await matrix.start_sync()
```

- [ ] **Step 5: Verify Agent test**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_agent.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/agent.py src/matrix_client.py src/app.py tests/test_agent.py
git commit -m "feat: wire matrix agent runtime"
```

---

## Task 9: Documentation, Cleanup, and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `README_EN.md`
- Modify: `.gitignore`
- Delete or leave unreferenced: `src/routers/*`, `src/services/webhook.py`, `link/*.yaml`
- Test: full suite

- [ ] **Step 1: Update README scope**

Rewrite the intro to state:

```markdown
# Matrix Todo Agent

这是一个 Matrix-first 的个人待办 Agent。项目不再提供 FastAPI REST API，也不再通过 webhook 连接 link；Matrix 是唯一用户交互入口，LLM 通过内置工具直接操作本地 JSON 数据。
```

Remove API endpoint tables, OpenAPI instructions, webhook curl examples, and `TODO_PORT` references.

- [ ] **Step 2: Update `.gitignore`**

Ensure runtime data and media are ignored:

```gitignore
.env
db/
downloads/
.pytest_cache/
__pycache__/
*.pyc
```

- [ ] **Step 3: Remove unused API files from runtime**

If tests no longer import routers, delete:

```text
src/routers/
src/services/webhook.py
link/config-template.yaml
link/todo-agent.yaml
```

If keeping files temporarily to reduce diff size, ensure no production import references them:

Run: `rg "src.routers|services.webhook|FastAPI|uvicorn|TODO_PORT|TODO_WEBHOOK_URL" src tests README.md .env.example Makefile`

Expected: no matches, except historical docs outside current README if intentionally retained.

- [ ] **Step 4: Run focused verification**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_config.py \
  tests/test_notification.py \
  tests/test_tool_registry.py \
  tests/test_todo_tools.py \
  tests/test_prompt_context.py \
  tests/test_llm_engine.py \
  tests/test_media_store.py \
  tests/test_agent.py \
  -v
```

Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `make test`

Expected: PASS. If legacy API tests fail because REST API was intentionally removed, replace them with service/tool-level tests rather than reintroducing FastAPI.

- [ ] **Step 6: Commit**

Run:

```bash
git add README.md README_EN.md .gitignore src tests .env.example requirements.txt Makefile prompts
git commit -m "docs: document matrix todo agent runtime"
```

---

## Execution Notes

- Do not restore FastAPI, Uvicorn, HTTP port configuration, or webhook delivery.
- Do not call todo functionality through local REST APIs; todo tools must use Python services directly.
- Do not persist non-text media in Matrix media repository; Matrix is the communication channel only.
- Treat existing uncommitted changes as user-owned unless a task explicitly touches the same file.
- If Matrix or R2 integration tests would require real credentials, keep those as unit tests with fakes and document manual verification steps in README.

## Manual Verification

After the full test suite passes:

- Copy `.env.example` to `.env` and fill Matrix, LLM, and R2 credentials.
- Run `make run`.
- Confirm logs show data dir, downloads dir, Matrix homeserver, rooms, registered tools, R2 enabled state, and scheduler startup.
- Send a Matrix text message asking the agent to create a task.
- Confirm the agent replies in Matrix and `db/tasks.json` contains the task.
- Send a reminder-triggering task or run the scheduler job manually and confirm Matrix receives the notification directly.
- Send an image/file and confirm it is classified under `downloads/imgs` or `downloads/files` when the corresponding download switch is enabled.
