import asyncio
from pathlib import Path

from src.agent import TodoAgent
from src.config import AppConfig, LLMConfig, MatrixConfig, MediaConfig, R2Config


class _FakeMatrixClient:
    def __init__(self) -> None:
        self.handler = None
        self.sent_messages: list[tuple[str, str]] = []
        self.typing_calls: list[tuple[str, bool]] = []

    def set_message_handler(self, callback):
        self.handler = callback

    async def send_text(self, room_id: str, text: str) -> None:
        self.sent_messages.append((room_id, text))

    async def set_typing(self, room_id: str, enabled: bool) -> None:
        self.typing_calls.append((room_id, enabled))

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class _FakeMediaStore:
    def __init__(self, image_path: Path | None = None) -> None:
        self.image_path = image_path
        self.downloaded: list[tuple[str, str]] = []

    async def download_r2_uri(self, uri: str, media_kind: str):
        self.downloaded.append((uri, media_kind))
        return self.image_path


class _FakeLLM:
    def __init__(self, should_fail: bool = False) -> None:
        self._vision_enabled = True
        self.should_fail = should_fail
        self.prompts: list[str] = []

    async def chat(self, room_id: str, prompt: str, system_prompt: str | None = None) -> str:
        self.prompts.append(prompt)
        if self.should_fail:
            raise RuntimeError("llm failure")
        return "ok"


def _config(tmp_path: Path) -> AppConfig:
    prompt_path = tmp_path / "prompts" / "system_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("系统提示词", encoding="utf-8")
    return AppConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / "db",
        downloads_dir=tmp_path / "downloads",
        prompt_path=prompt_path,
        skills_dir=None,
        matrix=MatrixConfig(
            homeserver="https://matrix.example",
            user="@todo:example",
            password="secret",
            rooms=["!room:example"],
        ),
        llm=LLMConfig(
            base_url="https://llm.example/v1",
            api_key="secret",
            model="demo",
            temperature=0.7,
            max_history=20,
            enable_thinking=False,
            vision_enabled=True,
        ),
        r2=R2Config(
            endpoint="https://example.r2",
            access_key="ak",
            secret_key="sk",
            bucket="bucket",
            public_url="",
        ),
        media=MediaConfig(
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


def test_compose_prompt_injects_downloaded_image_for_vision(tmp_path):
    matrix = _FakeMatrixClient()
    image_path = tmp_path / "downloads" / "imgs" / "hat.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"data")
    media_store = _FakeMediaStore(image_path=image_path)
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)

    prompt = asyncio.run(
        agent._compose_prompt(
            "![草帽](r2://bucket/imgs/hat.jpg)\n今天下午要买这个",
            [],
            "!room:example",
        )
    )

    assert "[image:" in prompt
    assert "今天下午要买这个" in prompt
    assert media_store.downloaded == [("r2://bucket/imgs/hat.jpg", "image")]


def test_handle_matrix_message_replies_with_fallback_on_exception(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM(should_fail=True)
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "完成这个任务", []))

    assert len(matrix.sent_messages) == 1
    assert "出错" in matrix.sent_messages[0][1]
    assert matrix.typing_calls == [("!room:example", True), ("!room:example", False)]


def test_handle_matrix_message_sets_typing_while_processing(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "今天任务", []))

    assert matrix.typing_calls == [("!room:example", True), ("!room:example", False)]
    assert matrix.sent_messages == [("!room:example", "ok")]


def test_task_reminder_notification_uses_markdown_table(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=_FakeLLM())

    message = agent._format_notification(
        {
            "type": "task_reminder",
            "data": {
                "task": {
                    "id": "26042802",
                    "title": "下载DJ",
                    "scheduled_at": "2026-04-28T18:15:00",
                    "detail": "下载抖音热歌DJ音频",
                    "completion_summary": "",
                    "minutes_before": 2,
                }
            },
        }
    )

    assert message.startswith("🔔 提前 2 分钟提醒")
    assert "提前 2 分钟提醒" in message
    assert "| ID | 标题 | 开始时间 | 详情 | 完成总结 |" in message
    assert (
        "| 26042802 | 下载DJ | 04-28 18:15 | 下载抖音热歌DJ音频 |  |"
        in message
    )
    assert "状态" not in message
    assert "优先级" not in message


def test_agenda_notifications_use_markdown_tables(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=_FakeLLM())

    message = agent._format_notification(
        {
            "type": "morning_agenda",
            "timestamp": "2026-04-28T08:00:00",
            "data": {
                "business_day": "2026-04-28",
                "today_tasks": [
                    {
                        "id": "26042801",
                        "title": "买草帽",
                        "scheduled_at": "2026-04-28T21:30:00",
                        "detail": "商店购买",
                        "completion_summary": "",
                    }
                ],
                "future_tasks": [
                    {
                        "id": "26042806",
                        "title": "成都爬山",
                        "scheduled_at": "2026-04-30T09:00:00",
                        "detail": "",
                        "completion_summary": "",
                    }
                ],
            },
        }
    )

    assert "今日任务：" in message
    assert "未来任务：" in message
    assert message.count("| ID | 标题 | 开始时间 | 详情 | 完成总结 |") == 2
    assert "| 26042801 | 买草帽 | 04-28 21:30 | 商店购买 |  |" in message
    assert "| 26042806 | 成都爬山 | 04-30 09:00 |  |  |" in message
    assert "状态" not in message
    assert "优先级" not in message
    assert "- ➖" not in message
