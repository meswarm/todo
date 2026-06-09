"""Application configuration loaded from .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(
    os.getenv("TODO_BASE_DIR", str(Path(__file__).resolve().parent.parent)),
).resolve()

PLACEHOLDER_VALUES = {
    "change-me",
    "https://matrix.example.com",
    "@todo-bot:example.com",
    "!room-id:example.com",
}

load_dotenv(BASE_DIR / ".env.example")
load_dotenv(BASE_DIR / ".env", override=True)


def parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse env var values commonly used as booleans."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _required_env(name: str) -> str:
    """Read a required environment variable and reject missing or blank values."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}，请检查项目根目录 .env")
    return value


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _int_list_env(name: str, default: str) -> list[int]:
    raw = os.getenv(name, default)
    values: list[int] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        values.append(int(item))
    return values


def _time_env(name: str, default: str) -> time:
    raw = os.getenv(name, default).strip()
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError(f"{name} must use HH:MM format")
    hour, minute = (int(part) for part in parts)
    return time(hour=hour, minute=minute)


def _resolve_with_base(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


@dataclass(frozen=True)
class MatrixConfig:
    homeserver: str
    user: str
    password: str
    rooms: list[str]
    typing_enabled: bool = True
    typing_timeout_ms: int = 30000


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
    downloads_dir: Path
    prompt_path: Path
    skills_dir: Path | None
    matrix: MatrixConfig
    llm: LLMConfig
    r2: R2Config
    media: MediaConfig
    morning_hour: int
    morning_minute: int
    noon_hour: int
    noon_minute: int
    evening_hour: int
    evening_minute: int
    task_reminders: list[int]
    reminder_min_lead_seconds: int
    slot_morning_time: time
    slot_afternoon_time: time
    slot_evening_time: time
    context_cell_max_chars: int

    @property
    def download_imgs_dir(self) -> Path:
        return self.downloads_dir / "imgs"

    @classmethod
    def from_env(cls) -> "AppConfig":
        base_dir = Path(os.getenv("TODO_BASE_DIR", str(BASE_DIR))).expanduser().resolve()
        data_dir = _resolve_with_base(
            os.getenv("TODO_DATA_DIR", str(base_dir / "db")),
            base_dir,
        )
        downloads_dir = _resolve_with_base(
            os.getenv("TODO_DOWNLOADS_DIR", str(base_dir / "downloads")),
            base_dir,
        )
        skills_raw = os.getenv("TODO_SKILLS_DIR", "").strip()
        skills_dir = _resolve_with_base(skills_raw, base_dir) if skills_raw else None
        return cls(
            base_dir=base_dir,
            data_dir=data_dir,
            downloads_dir=downloads_dir,
            prompt_path=_resolve_with_base(
                os.getenv(
                    "TODO_SYSTEM_PROMPT",
                    str(base_dir / "prompts" / "system_prompt.md"),
                ),
                base_dir,
            ),
            skills_dir=skills_dir,
            matrix=MatrixConfig(
                homeserver=_required_env("MATRIX_HOMESERVER"),
                user=_required_env("MATRIX_USER"),
                password=_required_env("MATRIX_PASSWORD"),
                rooms=_csv_env("MATRIX_ROOMS"),
                typing_enabled=parse_bool(os.getenv("MATRIX_TYPING_ENABLED"), True),
                typing_timeout_ms=int(os.getenv("MATRIX_TYPING_TIMEOUT_MS", "30000")),
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
            morning_hour=int(os.getenv("TODO_MORNING_HOUR", "7")),
            morning_minute=int(os.getenv("TODO_MORNING_MINUTE", "0")),
            noon_hour=int(os.getenv("TODO_NOON_HOUR", "12")),
            noon_minute=int(os.getenv("TODO_NOON_MINUTE", "0")),
            evening_hour=int(os.getenv("TODO_EVENING_HOUR", "23")),
            evening_minute=int(os.getenv("TODO_EVENING_MINUTE", "0")),
            task_reminders=_int_list_env("TODO_REMINDERS", "10,5,2"),
            reminder_min_lead_seconds=int(os.getenv("TODO_REMINDER_MIN_LEAD_SECONDS", "30")),
            slot_morning_time=_time_env("TODO_SLOT_MORNING_TIME", "08:00"),
            slot_afternoon_time=_time_env("TODO_SLOT_AFTERNOON_TIME", "14:00"),
            slot_evening_time=_time_env("TODO_SLOT_EVENING_TIME", "18:00"),
            context_cell_max_chars=int(os.getenv("TODO_CONTEXT_CELL_MAX_CHARS", "300")),
        )


APP_CONFIG = AppConfig.from_env()

DATA_DIR = APP_CONFIG.data_dir
TASKS_FILE = DATA_DIR / "tasks.json"
HISTORY_FILE = DATA_DIR / "history.json"
RECURRENCES_FILE = DATA_DIR / "recurrences.json"
REMINDER_STATE_FILE = DATA_DIR / "reminder_state.json"
MORNING_PUSH_HOUR = APP_CONFIG.morning_hour
MORNING_PUSH_MINUTE = APP_CONFIG.morning_minute
NOON_PUSH_HOUR = APP_CONFIG.noon_hour
NOON_PUSH_MINUTE = APP_CONFIG.noon_minute
EVENING_PUSH_HOUR = APP_CONFIG.evening_hour
EVENING_PUSH_MINUTE = APP_CONFIG.evening_minute
TASK_REMINDER_MINUTES = APP_CONFIG.task_reminders
REMINDER_MIN_LEAD_SECONDS = APP_CONFIG.reminder_min_lead_seconds
SLOT_REMINDER_TIMES = {
    "morning": APP_CONFIG.slot_morning_time,
    "afternoon": APP_CONFIG.slot_afternoon_time,
    "evening": APP_CONFIG.slot_evening_time,
}
CONTEXT_CELL_MAX_CHARS = APP_CONFIG.context_cell_max_chars


def ensure_data_dirs() -> None:
    """Create required directories and initialize default JSON files."""
    for directory in [
        DATA_DIR,
        APP_CONFIG.download_imgs_dir,
        APP_CONFIG.downloads_dir / "videos",
        APP_CONFIG.downloads_dir / "audios",
        APP_CONFIG.downloads_dir / "files",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    for file_path in [TASKS_FILE, HISTORY_FILE, RECURRENCES_FILE]:
        if not file_path.exists():
            file_path.write_text("[]", encoding="utf-8")
    if not REMINDER_STATE_FILE.exists():
        REMINDER_STATE_FILE.write_text("{}", encoding="utf-8")


def validate_runtime_config(config: AppConfig = APP_CONFIG) -> None:
    """Reject template values before opening long-running network clients."""
    checks = {
        "MATRIX_HOMESERVER": config.matrix.homeserver,
        "MATRIX_USER": config.matrix.user,
        "MATRIX_PASSWORD": config.matrix.password,
        "LLM_API_KEY": config.llm.api_key,
    }
    missing_or_placeholder = [
        name
        for name, value in checks.items()
        if not value or value.strip() in PLACEHOLDER_VALUES
    ]
    if not config.matrix.rooms or any(room in PLACEHOLDER_VALUES for room in config.matrix.rooms):
        missing_or_placeholder.append("MATRIX_ROOMS")
    if config.llm.base_url in PLACEHOLDER_VALUES or not config.llm.base_url:
        missing_or_placeholder.append("LLM_BASE_URL")
    if not config.llm.model:
        missing_or_placeholder.append("LLM_MODEL")

    if missing_or_placeholder:
        names = ", ".join(sorted(set(missing_or_placeholder)))
        raise RuntimeError(f".env 仍包含缺失或示例配置，请先设置: {names}")
