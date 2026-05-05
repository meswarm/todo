[![语言-中文](README.md)](README.md)
[![Language-English](README_EN.md)](README_EN.md)

# Todo Matrix Agent

Matrix-first personal task agent. Matrix is the only user-facing channel, the LLM handles intent parsing and tool calls, tasks are stored in local JSON files, and media can be referenced with `r2://...` links.

## Core Features

- Create, query, update, and complete tasks
- Recurring task rules with date-based projection
- Morning agenda, evening review, and unified reminders
- Markdown and `r2://...` media link handling
- Matrix runtime, tool calling, and JSON persistence

## Runtime

- `make run` starts a single process by executing `src.main -> src.app.main()`.
- `src.main` is only a command entrypoint and contains no FastAPI/Uvicorn code.
- `src.app.run()` does:
  - `ensure_data_dirs()` bootstrap
  - bootstrap `TodoAgent` (Matrix client + LLM + tools)
  - `start_scheduler()` / `stop_scheduler()` lifecycle handling
  - wait on the event loop until shutdown

## Core Components

- `src.app` boots the runtime and scheduler.
- `src.agent` routes Matrix messages to the LLM and executes tools.
- `src.matrix_client` is a lightweight Matrix wrapper.
- `src.llm_engine` manages OpenAI-compatible inference with tool-calling.
- `src.tool_registry` registers built-in tools (`create_task`, `get_task`, `list_tasks`, `search_tasks`, `complete_task`, `get_agenda`).
- `src.media_store` handles local downloads and R2 access.

## Quick Start

```bash
cp .env.example .env
make init
make run
```

Without make:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m src.main
```

## Key Environment Variables

- `TODO_DATA_DIR`: JSON data directory (default `./db`)
- `TODO_DOWNLOADS_DIR`: media download directory (default `./downloads`, subfolders `imgs/videos/audios/files`)
- `TODO_SYSTEM_PROMPT`: path to system prompt file, default `./prompts/system_prompt.md`
- `TODO_SKILLS_DIR`: optional skills directory
- `MATRIX_HOMESERVER`, `MATRIX_USER`, `MATRIX_PASSWORD`, `MATRIX_ROOMS`: Matrix config
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`: LLM config for agent reasoning
- `LLM_VISION_ENABLED`: `true/false`, enables multimodal image understanding
- `R2_ENDPOINT`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET`, `R2_PUBLIC_URL`: R2 config
- `R2_DOWNLOAD_IMAGES`, `R2_DOWNLOAD_VIDEOS`, `R2_DOWNLOAD_AUDIOS`, `R2_DOWNLOAD_FILES`: `true/false` download switches
- `TODO_MORNING_HOUR`, `TODO_MORNING_MINUTE`: morning run time
- `TODO_EVENING_HOUR`, `TODO_EVENING_MINUTE`: evening run time
- `TODO_REMINDERS`: unified reminder minute list, for example `10,5,2`

## Directory Layout

```text
.
├── src/
│   ├── tools/
│   ├── services/
│   └── scheduler/
├── prompts/system_prompt.md
├── tests/
├── .env.example
├── requirements.txt
├── Makefile
└── README_EN.md
```

## Tests

```bash
make test
```

## Prompt file

- Default prompt file: `prompts/system_prompt.md`.
