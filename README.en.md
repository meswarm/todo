# Todo Matrix Agent

[中文](README.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Matrix](https://img.shields.io/badge/Matrix-bot-blue)
![Storage](https://img.shields.io/badge/storage-local_JSON-green)
![License](https://img.shields.io/badge/license-MIT-green)

Todo Matrix Agent is a Matrix-first personal task bot. It receives and sends messages through Matrix, uses an LLM only for complex intent handling such as task creation, task updates, and recurrence rules, and handles explicit commands, reminders, reports, and Markdown table rendering in deterministic code. Tasks, history, recurrence rules, and reminder dedupe state are stored as local JSON files by default.

## Features

- Create and update tasks from natural language, including image, audio, video, and file links preserved in task details.
- Deterministic shortcut commands that bypass the LLM: `list today`, `list next`, `list history N`, `delete ID`, and `complete ID`.
- One-off tasks and recurrence rules, with create, update, and delete support for recurrence rules.
- Exact-time tasks and flexible slot tasks: morning, afternoon, and evening.
- Exact-time tasks use `TODO_REMINDERS`; flexible slot tasks are grouped by configurable slot anchor times.
- Morning and noon reports for today's tasks, plus an evening report for tomorrow's tasks.
- Active notification messages include `com.talk.kind=notification` metadata for Matrix client highlighting.
- Local history archive with `list history N` for reviewing previous days.

## Requirements

- Python 3.10 or newer. The project currently runs and tests on Python 3.12.
- A Matrix account and room.
- An OpenAI-compatible Chat Completions model provider.
- Optional: Cloudflare R2 or a compatible object store for media links and downloads.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at least the Matrix and LLM values:

```bash
MATRIX_HOMESERVER=https://matrix.example.com
MATRIX_USER=@todo-bot:example.com
MATRIX_PASSWORD=change-me
MATRIX_ROOMS=!room-id:example.com
LLM_BASE_URL=https://example.com/compatible-mode/v1
LLM_API_KEY=change-me
LLM_MODEL=model-name
```

Start the bot:

```bash
make run
```

Without Makefile:

```bash
PYTHONPATH=. .venv/bin/python -m src.main
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `TODO_BASE_DIR` | `.` | Base directory for relative paths |
| `TODO_DATA_DIR` | `./db` | Tasks, history, recurrence rules, and reminder state |
| `TODO_DOWNLOADS_DIR` | `./downloads` | Media download directory |
| `TODO_SYSTEM_PROMPT` | `./prompts/system_prompt.md` | System prompt path |
| `TODO_SKILLS_DIR` | empty | Optional skills directory |
| `TODO_CONTEXT_CELL_MAX_CHARS` | `300` | Max rendered table cell length |
| `MATRIX_HOMESERVER` | example value | Matrix homeserver |
| `MATRIX_USER` | example value | Matrix bot account |
| `MATRIX_PASSWORD` | `change-me` | Matrix account password |
| `MATRIX_ROOMS` | example value | Allowed room IDs, comma-separated |
| `MATRIX_TYPING_ENABLED` | `true` | Whether to send typing notifications |
| `MATRIX_TYPING_TIMEOUT_MS` | `30000` | Typing timeout in milliseconds |
| `LLM_BASE_URL` | example value | OpenAI-compatible base URL |
| `LLM_API_KEY` | `change-me` | LLM API key |
| `LLM_MODEL` | example value | Model name |
| `LLM_TEMPERATURE` | `0.7` | Model temperature |
| `LLM_MAX_HISTORY` | `20` | Conversation history length |
| `LLM_ENABLE_THINKING` | `false` | Whether to pass the model thinking option |
| `LLM_VISION_ENABLED` | `false` | Whether image understanding is enabled |
| `R2_ENDPOINT` | empty | R2 or compatible object-store endpoint |
| `R2_ACCESS_KEY` | empty | R2 access key |
| `R2_SECRET_KEY` | empty | R2 secret key |
| `R2_BUCKET` | `todo-media` | R2 bucket |
| `R2_PUBLIC_URL` | empty | Public R2 URL |
| `R2_DOWNLOAD_IMAGES` | `true` | Download image files |
| `R2_DOWNLOAD_VIDEOS` | `true` | Download video files |
| `R2_DOWNLOAD_AUDIOS` | `true` | Download audio files |
| `R2_DOWNLOAD_FILES` | `true` | Download generic files |
| `TODO_MORNING_HOUR` / `TODO_MORNING_MINUTE` | `7` / `0` | Morning report time for today's tasks |
| `TODO_NOON_HOUR` / `TODO_NOON_MINUTE` | `12` / `0` | Noon report time for today's tasks |
| `TODO_EVENING_HOUR` / `TODO_EVENING_MINUTE` | `23` / `0` | Evening report time for tomorrow's tasks |
| `TODO_REMINDERS` | `10,5,2` | Lead minutes for exact-time task reminders |
| `TODO_REMINDER_MIN_LEAD_SECONDS` | `30` | Skip reminders too close to task start |
| `TODO_SLOT_MORNING_TIME` | `08:00` | Morning slot reminder anchor |
| `TODO_SLOT_AFTERNOON_TIME` | `14:00` | Afternoon slot reminder anchor |
| `TODO_SLOT_EVENING_TIME` | `18:00` | Evening slot reminder anchor |

## Usage

Shortcut commands:

| Command | Behavior |
| --- | --- |
| `list today` | Return today's tasks as a Markdown table |
| `list next` | Return tomorrow's tasks, future active one-off tasks, and recurrence rules |
| `list history 2` | Return historical tasks for the past 2 days, grouped by date |
| `delete 26053101` | Delete a concrete task |
| `delete rec_20260428_001` | Delete a recurrence rule |
| `complete 26053101` | Mark today's task as completed; the start-time column shows `✅` |

Natural-language examples:

```text
Buy groceries tonight
Go to the supermarket tomorrow afternoon
Buy durian today at 20:00
Move 26053108 to tomorrow morning
Change the daily cat litter and feeding task to every morning
```

Time semantics:

- If the user gives a concrete time, the task is exact-time, for example `05-31 20:00`.
- If the user gives only morning, afternoon, or evening, the task is a flexible slot task, for example `05-31 afternoon`.
- If neither a concrete time nor a slot is clear, the LLM should ask whether the task belongs to morning, afternoon, or evening.

## Development

```bash
make test
```

Or run pytest directly:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/ -m "not api" -v
```

Project layout:

```text
.
├── src/
│   ├── app.py              # Runtime entrypoint
│   ├── agent.py            # Matrix + LLM + tool orchestration
│   ├── matrix_client.py    # Matrix client wrapper
│   ├── llm_engine.py       # OpenAI-compatible inference and tool calls
│   ├── media_store.py      # R2/local media handling
│   ├── tools/              # Todo tool definitions
│   ├── services/           # Task service, notification queue, business-day logic
│   └── scheduler/          # Recurrence generation, reminders, reports
├── prompts/
│   └── system_prompt.md
├── tests/
├── .env.example
├── requirements.txt
└── Makefile
```

## Privacy And Security

- Do not commit `.env`, local `db/`, `downloads/`, virtual environments, caches, or temporary files.
- `.env.example` contains placeholders and safe defaults only.
- If real Matrix passwords, LLM keys, or R2 keys were ever committed to public history, rotate them immediately.
- R2 media links are stored in task details for client rendering; do not commit local data files that contain personal media links.

## License

This project is released under the [MIT License](LICENSE).
