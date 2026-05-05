from pathlib import Path

import importlib
import sys


def _load_config(monkeypatch, base_dir: Path):
    monkeypatch.setenv("TODO_BASE_DIR", str(base_dir))
    monkeypatch.setenv("TODO_DATA_DIR", str(base_dir / "db"))
    monkeypatch.setenv("TODO_DOWNLOADS_DIR", str(base_dir / "downloads"))
    monkeypatch.setenv("MATRIX_HOMESERVER", "https://matrix.example")
    monkeypatch.setenv("MATRIX_USER", "@todo:example")
    monkeypatch.setenv("MATRIX_PASSWORD", "secret")
    monkeypatch.setenv("MATRIX_ROOMS", "!room:example,!ops:example")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "llm-secret")
    monkeypatch.setenv("LLM_MODEL", "qwen-plus")
    monkeypatch.setenv("LLM_VISION_ENABLED", "false")
    sys.modules.pop("src.config", None)
    return importlib.import_module("src.config")


def test_parse_bool_accepts_common_true_values(monkeypatch, tmp_path):
    config = _load_config(monkeypatch, tmp_path)
    assert config.parse_bool("1") is True
    assert config.parse_bool("true") is True
    assert config.parse_bool("yes") is True
    assert config.parse_bool("on") is True


def test_parse_bool_accepts_common_false_values(monkeypatch, tmp_path):
    config = _load_config(monkeypatch, tmp_path)
    assert config.parse_bool("0") is False
    assert config.parse_bool("false") is False
    assert config.parse_bool("no") is False
    assert config.parse_bool("off") is False
    assert config.parse_bool("") is False


def test_parse_bool_default_value(monkeypatch, tmp_path):
    config = _load_config(monkeypatch, tmp_path)
    assert config.parse_bool(None, True) is True
    assert config.parse_bool("unexpected", False) is False


def test_app_config_defaults_to_db_and_downloads(monkeypatch, tmp_path):
    monkeypatch.delenv("TODO_CONTEXT_CELL_MAX_CHARS", raising=False)
    config = _load_config(monkeypatch, tmp_path)

    assert config.APP_CONFIG.data_dir == tmp_path / "db"
    assert config.APP_CONFIG.downloads_dir == tmp_path / "downloads"
    assert config.APP_CONFIG.download_imgs_dir == tmp_path / "downloads" / "imgs"
    assert config.APP_CONFIG.matrix.rooms == ["!room:example", "!ops:example"]
    assert config.APP_CONFIG.matrix.typing_enabled is True
    assert config.APP_CONFIG.matrix.typing_timeout_ms == 30000
    assert config.APP_CONFIG.llm.vision_enabled is False
    assert config.APP_CONFIG.media.download_files is True
    assert config.APP_CONFIG.media.download_images is True
    assert config.APP_CONFIG.media.download_videos is True
    assert config.APP_CONFIG.media.download_audios is True
    assert config.APP_CONFIG.prompt_path == Path(tmp_path / "prompts" / "system_prompt.md")
    assert config.APP_CONFIG.task_reminders == [10, 5, 2]
    assert config.APP_CONFIG.reminder_min_lead_seconds == 30
    assert config.APP_CONFIG.context_cell_max_chars == 300
    assert config.CONTEXT_CELL_MAX_CHARS == 300


def test_app_config_parses_custom_reminder_minutes(monkeypatch, tmp_path):
    monkeypatch.setenv("TODO_REMINDERS", "30,15,5")
    monkeypatch.setenv("TODO_REMINDER_MIN_LEAD_SECONDS", "45")
    config = _load_config(monkeypatch, tmp_path)

    assert config.APP_CONFIG.task_reminders == [30, 15, 5]
    assert config.APP_CONFIG.reminder_min_lead_seconds == 45


def test_app_config_parses_context_cell_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("TODO_CONTEXT_CELL_MAX_CHARS", "500")
    config = _load_config(monkeypatch, tmp_path)

    assert config.APP_CONFIG.context_cell_max_chars == 500
    assert config.CONTEXT_CELL_MAX_CHARS == 500


def test_app_config_parses_matrix_typing_options(monkeypatch, tmp_path):
    monkeypatch.setenv("MATRIX_TYPING_ENABLED", "false")
    monkeypatch.setenv("MATRIX_TYPING_TIMEOUT_MS", "5000")
    config = _load_config(monkeypatch, tmp_path)

    assert config.APP_CONFIG.matrix.typing_enabled is False
    assert config.APP_CONFIG.matrix.typing_timeout_ms == 5000


def test_runtime_config_rejects_template_values(monkeypatch, tmp_path):
    config = _load_config(monkeypatch, tmp_path)
    bad_config = config.AppConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / "db",
        downloads_dir=tmp_path / "downloads",
        prompt_path=tmp_path / "prompts" / "system_prompt.md",
        skills_dir=None,
        matrix=config.MatrixConfig(
            homeserver="https://matrix.example.com",
            user="@todo-bot:example.com",
            password="change-me",
            rooms=["!room-id:example.com"],
        ),
        llm=config.LLMConfig(
            base_url="https://llm.example/v1",
            api_key="change-me",
            model="qwen-plus",
            temperature=0.7,
            max_history=20,
            enable_thinking=False,
            vision_enabled=False,
        ),
        r2=config.R2Config(endpoint="", access_key="", secret_key="", bucket="todo-media", public_url=""),
        media=config.MediaConfig(
            downloads_dir=tmp_path / "downloads",
            download_images=True,
            download_videos=True,
            download_audios=True,
            download_files=True,
        ),
        morning_hour=8,
        morning_minute=0,
        evening_hour=21,
        evening_minute=0,
        task_reminders=[10, 5, 2],
        reminder_min_lead_seconds=30,
        context_cell_max_chars=300,
    )

    try:
        config.validate_runtime_config(bad_config)
    except RuntimeError as exc:
        assert "MATRIX_HOMESERVER" in str(exc)
        assert "MATRIX_ROOMS" in str(exc)
        assert "LLM_API_KEY" in str(exc)
    else:
        raise AssertionError("template config should be rejected")
