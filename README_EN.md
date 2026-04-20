[![语言-中文](https://img.shields.io/badge/语言-中文-green)](README.md)
[![Language-English](https://img.shields.io/badge/Language-English-blue)](README_EN.md)

# Todo API (Personal Task & Schedule Service)

> A lightweight, self-hosted task and schedule backend: REST API, JSON persistence, scheduled jobs, and Webhook notifications. Pairs well with the [Link](https://github.com/txl/link) middleware for AI-assisted workflows.

Defaults are loaded from `.env.example` / `.env` at the project root; **service ports are not hardcoded in application code**.

## Features

- **Tasks** — Full CRUD and four-state workflow (pending → in_progress → completed/abandoned)
- **Priority** — Urgency × importance × difficulty, plus estimated duration
- **Subtasks & dependencies** — One level of subtasks and dependency-aware ordering
- **Reminders** — Flexible (e.g. 30 minutes before) vs time-critical (e.g. 5/2/1 minutes before)
- **Recurrence** — Daily / weekly / monthly / interval rules
- **Detail docs** — Markdown attachments for longer context and media links
- **Search** — Active tasks and history
- **Agenda** — Dependency-aware, priority-aware schedule view
- **Scheduled pushes** — Morning agenda, evening review, instant reminders
- **Stats** — Daily / weekly / monthly snapshots

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.12+ |
| Web | FastAPI, Uvicorn |
| Data | Pydantic v2, JSON file storage (filelock) |
| Scheduling | APScheduler |
| Integration | httpx (Webhooks), python-dotenv (`.env`) |

## Getting Started

### Prerequisites

- Python 3.12+
- `make` (optional, for convenience targets)

### Install & Run

```bash
git clone https://github.com/OWNER/REPO.git
cd REPO

make init
make run
```

Replace `OWNER/REPO` with your GitHub user/org and repository name. The default listen port is defined in `.env.example` as `TODO_PORT`.

Without `make`:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PYTHONPATH=. python -m src.main
```

`make run` and `make test` **do not** create a virtual environment automatically; run `make init` first if `.venv` is missing.

### Configuration

The app loads `.env.example` first (repository defaults), then `.env` (local overrides).

```bash
cp .env.example .env
# Edit .env for your machine. Do not commit secrets.
```

`.env` is gitignored. **Do not** put real API keys, private URLs, or machine-specific absolute paths in the README.

`link/todo-agent.yaml` uses `${TODO_PORT}` in REST tool URLs. When starting Link (`ltool`), export the same `TODO_PORT` as in `.env`, e.g. `export TODO_PORT=48890`.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `TODO_DATA_DIR` | Data directory (default `./data`, gitignored) |
| `TODO_HOST` | Bind address (see `.env.example`) |
| `TODO_PORT` | Listen port (see `.env.example`) |
| `TODO_WEBHOOK_URL` | Full Webhook URL (see `.env.example`) |
| `TODO_MORNING_HOUR` / `TODO_MORNING_MINUTE` | Morning push time |
| `TODO_EVENING_HOUR` / `TODO_EVENING_MINUTE` | Evening push time |

See `.env.example` for authoritative default values.

## Project Layout

```text
.
├── .env.example          # Env template (copy to .env)
├── LICENSE
├── Makefile              # make init / run / test / clean
├── README.md / README_EN.md
├── requirements.txt
├── src/                  # Application code
├── tests/                # pytest
├── link/                 # Link integration examples (replace secrets before publishing)
├── docs/                 # Design & planning notes
│   ├── plans/
│   └── superpowers/
└── data/                 # Runtime data (gitignored by default)
```

The `media_cache/` directory is gitignored; do not commit downloaded media.

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tasks` | Create task |
| `GET` | `/tasks` | List (filters) |
| `GET` | `/tasks/{id}` | Get one |
| `PUT` | `/tasks/{id}` | Update |
| `DELETE` | `/tasks/{id}` | Delete |
| `PATCH` | `/tasks/{id}/status` | Change status |
| `POST` | `/tasks/{id}/subtasks` | Add subtask |
| `POST` | `/tasks/{id}/notes` | Add note |
| `PUT` / `GET` | `/tasks/{id}/detail` | Write / read Markdown detail |
| `PUT` | `/tasks/{id}/reminders` | Set reminders |
| `PUT` | `/tasks/{id}/dependencies` | Set dependencies |
| `GET` | `/tasks/search?q=…` | Search |
| `GET` | `/agenda` | Agenda view |
| `POST` / `GET` | `/recurrences` | Recurrence rules |
| `GET` | `/stats/daily` etc. | Statistics |

OpenAPI UI: `http://localhost:<TODO_PORT>/docs` after startup.

## Tests

```bash
make test
```

## Contributing

1. Fork the repository  
2. Create a branch: `git checkout -b feat/your-feature`  
3. Commit: `git commit -m 'feat: describe change'`  
4. Push: `git push origin feat/your-feature`  
5. Open a Pull Request  

## Security Notes (before publishing)

- If `link/todo-agent.yaml` contains Matrix credentials or room IDs, **redact or replace** them before pushing to a **public** repository, and rotate any exposed secrets.  
- Verify you are not committing `.env`, `data/`, `media_cache/`, or key material.

## License

MIT — see [LICENSE](LICENSE).
