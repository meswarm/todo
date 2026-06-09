import asyncio
from datetime import date, datetime, time
from pathlib import Path

import src.tools.todo_tools as todo_tools
from src.agent import TodoAgent
from src.config import AppConfig, LLMConfig, MatrixConfig, MediaConfig, R2Config
from src.models import Recurrence, RecurrencePattern, RecurrenceTemplate, Task, TimeKind, TimeSlot
from src.services import task_service
from src.services.notification import get_notification_sink


class _FakeMatrixClient:
    def __init__(self) -> None:
        self.handler = None
        self.sent_messages: list[tuple[str, str]] = []
        self.sent_message_extras: list[dict | None] = []
        self.typing_calls: list[tuple[str, bool]] = []

    def set_message_handler(self, callback):
        self.handler = callback

    async def send_text(self, room_id: str, text: str, content_extra=None) -> None:
        self.sent_messages.append((room_id, text))
        self.sent_message_extras.append(content_extra)

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
        noon_hour=12,
        noon_minute=0,
        evening_hour=21,
        evening_minute=0,
        task_reminders=[10, 5, 2],
        reminder_min_lead_seconds=30,
        slot_morning_time=time(8, 0),
        slot_afternoon_time=time(14, 0),
        slot_evening_time=time(18, 0),
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

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "修改这个任务", []))

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


def test_list_today_command_returns_tasks_without_llm(monkeypatch, tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)
    task = Task(
        id="26053101",
        title="买菜",
        scheduled_at=datetime(2026, 5, 31, 9, 0),
        detail="青菜",
    )

    monkeypatch.setattr(todo_tools, "business_date", lambda now=None: date(2026, 5, 31))
    monkeypatch.setattr(task_service.task_store, "load_all", lambda: [task])
    monkeypatch.setattr(todo_tools, "list_recurrences", lambda enabled_only=False: [])

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "list today", []))

    assert llm.prompts == []
    assert matrix.typing_calls == []
    assert len(matrix.sent_messages) == 1
    message = matrix.sent_messages[0][1]
    assert "今日任务" in message
    assert "| ID | 标题 | 开始时间 | 详情 |" in message
    assert "| 26053101 | 买菜 | 05-31 09:00 | 青菜 |" in message


def test_list_tomorrow_command_uses_llm_after_shortcut_removed(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "list tomorrow", []))

    assert llm.prompts == ["list tomorrow"]
    assert matrix.typing_calls == [("!room:example", True), ("!room:example", False)]
    assert matrix.sent_messages == [("!room:example", "ok")]


def test_list_next_command_separates_tomorrow_future_and_recurring(monkeypatch, tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)
    tomorrow = Task(
        id="26053103",
        title="明日事",
        scheduled_at=datetime(2026, 6, 1, 8, 0),
    )
    day_after = Task(
        id="26053104",
        title="后天事",
        scheduled_at=datetime(2026, 6, 2, 8, 0),
    )
    recurring_instance = Task(
        id="26053105",
        title="周期实例",
        scheduled_at=datetime(2026, 6, 2, 9, 0),
        recurrence_id="rec_260531_002",
    )
    recurrence = Recurrence(
        id="rec_260531_002",
        title="每周复盘",
        pattern=RecurrencePattern.WEEKLY,
        week_days=[1],
        time_of_day="20:00",
        start_date=date(2026, 5, 1),
        template=RecurrenceTemplate(title="复盘", detail="写总结"),
    )

    monkeypatch.setattr(todo_tools, "business_date", lambda now=None: date(2026, 5, 31))
    monkeypatch.setattr(
        task_service.task_store,
        "load_all",
        lambda: [tomorrow, day_after, recurring_instance],
    )
    monkeypatch.setattr(todo_tools, "list_recurrences", lambda enabled_only=False: [recurrence])

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "list next", []))

    assert llm.prompts == []
    message = matrix.sent_messages[0][1]
    assert "明日任务" in message
    assert "| 26053103 | 明日事 | 06-01 08:00 |  |" in message
    assert "未来任务" in message
    assert "| 26053104 | 后天事 | 06-02 08:00 |  |" in message
    assert "26053105" not in message
    assert "周期任务规则" in message
    assert "| ID | 标题 | 周期 | 模板任务 | 详情 |" in message
    assert "| rec_260531_002 | 每周复盘 | 每周周一 20:00 | 复盘 | 写总结 |" in message


def test_list_history_command_returns_recent_history_by_day_without_llm(monkeypatch, tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)
    yesterday_late = Task(
        id="26053002",
        title="买水",
        scheduled_at=datetime(2026, 5, 30, 21, 0),
        detail="矿泉水",
    )
    yesterday_early = Task(
        id="26053001",
        title="寄快递",
        scheduled_at=datetime(2026, 5, 30, 9, 0),
    )
    day_before = Task(
        id="26052901",
        title="洗衣服",
        scheduled_at=datetime(2026, 5, 29, 20, 0),
    )
    older = Task(
        id="26052801",
        title="旧任务",
        scheduled_at=datetime(2026, 5, 28, 20, 0),
    )

    monkeypatch.setattr(todo_tools, "business_date", lambda now=None: date(2026, 5, 31))
    monkeypatch.setattr(
        task_service.history_store,
        "load_all",
        lambda: [older, yesterday_late, day_before, yesterday_early],
    )

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "list history 2", []))

    assert llm.prompts == []
    assert matrix.typing_calls == []
    message = matrix.sent_messages[0][1]
    assert "历史任务 2026-05-30" in message
    assert "历史任务 2026-05-29" in message
    assert "| 26053001 | 寄快递 | 05-30 09:00 |  |" in message
    assert "| 26053002 | 买水 | 05-30 21:00 | 矿泉水 |" in message
    assert "| 26052901 | 洗衣服 | 05-29 20:00 |  |" in message
    assert "26052801" not in message
    assert message.index("历史任务 2026-05-30") < message.index("历史任务 2026-05-29")
    assert message.index("26053001") < message.index("26053002")


def test_invalid_list_history_command_uses_llm(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "list history two", []))

    assert llm.prompts == ["list history two"]
    assert matrix.typing_calls == [("!room:example", True), ("!room:example", False)]
    assert matrix.sent_messages == [("!room:example", "ok")]


def test_delete_task_command_deletes_real_task_without_llm(monkeypatch, tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)
    deleted: list[str] = []

    monkeypatch.setattr(todo_tools, "business_date", lambda now=None: date(2026, 5, 31))
    monkeypatch.setattr(task_service, "delete_task", lambda task_id: deleted.append(task_id) or True)
    monkeypatch.setattr(task_service.task_store, "load_all", lambda: [])
    monkeypatch.setattr(todo_tools, "list_recurrences", lambda enabled_only=False: [])

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "delete 26053101", []))

    assert llm.prompts == []
    assert matrix.typing_calls == []
    assert deleted == ["26053101"]
    message = matrix.sent_messages[0][1]
    assert message == "已删除任务 `26053101`"
    assert "今日任务" not in message
    assert "明日任务" not in message
    assert "未来任务" not in message
    assert "周期任务规则" not in message


def test_delete_recurring_task_instance_suppresses_same_day_projection(monkeypatch, tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)
    task = Task(
        id="26060301",
        title="铲屎喂粮",
        scheduled_at=datetime(2026, 6, 3, 8, 0),
        recurrence_id="rec_20260428_001",
    )
    skipped: list[tuple[str, date]] = []

    monkeypatch.setattr(todo_tools, "business_date", lambda now=None: date(2026, 6, 3))
    monkeypatch.setattr(task_service, "get_task", lambda task_id: task if task_id == task.id else None)
    monkeypatch.setattr(task_service, "delete_task", lambda task_id: True)
    monkeypatch.setattr(task_service.task_store, "load_all", lambda: [])
    monkeypatch.setattr(todo_tools, "list_recurrences", lambda enabled_only=False: [])
    import src.agent as agent_module

    monkeypatch.setattr(
        agent_module,
        "skip_recurrence_occurrence",
        lambda recurrence_id, day: skipped.append((recurrence_id, day)) or True,
    )

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "delete 26060301", []))

    assert llm.prompts == []
    assert skipped == [("rec_20260428_001", date(2026, 6, 3))]


def test_complete_task_command_marks_task_done_without_llm(monkeypatch, tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)
    task = Task(
        id="26053101",
        title="买菜",
        scheduled_at=datetime(2026, 5, 31, 14, 0),
        detail="青菜",
    )
    completed: list[str] = []

    def fake_complete(task_id: str):
        completed.append(task_id)
        task.completed = True
        return task

    monkeypatch.setattr(todo_tools, "business_date", lambda now=None: date(2026, 5, 31))
    monkeypatch.setattr(task_service, "complete_task", fake_complete)
    monkeypatch.setattr(task_service.task_store, "load_all", lambda: [task])
    monkeypatch.setattr(todo_tools, "list_recurrences", lambda enabled_only=False: [])

    asyncio.run(agent.handle_matrix_message("!room:example", "@user:example", "complete 26053101", []))

    assert llm.prompts == []
    assert matrix.typing_calls == []
    assert completed == ["26053101"]
    message = matrix.sent_messages[0][1]
    assert "已完成任务 `26053101`" in message
    assert "| 26053101 | 买菜 | ✅ | 青菜 |" in message


def test_delete_recurring_rule_command_deletes_recurrence_without_llm(monkeypatch, tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    llm = _FakeLLM()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=llm)
    deleted: list[str] = []

    monkeypatch.setattr(todo_tools, "business_date", lambda now=None: date(2026, 5, 31))
    monkeypatch.setattr(todo_tools, "delete_recurrence", lambda recurrence_id: deleted.append(recurrence_id) or True)
    monkeypatch.setattr(task_service.task_store, "load_all", lambda: [])
    monkeypatch.setattr(todo_tools, "list_recurrences", lambda enabled_only=False: [])

    asyncio.run(
        agent.handle_matrix_message(
            "!room:example",
            "@user:example",
            "delete rec_20260531_001",
            [],
        )
    )

    assert llm.prompts == []
    assert deleted == ["rec_20260531_001"]
    message = matrix.sent_messages[0][1]
    assert message == "已删除周期任务规则 `rec_20260531_001`"
    assert "明日任务" not in message
    assert "未来任务" not in message
    assert "周期任务规则\n" not in message


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
                    "minutes_before": 2,
                }
            },
        }
    )

    assert message.startswith("## 🔔 提前 2 分钟提醒")
    assert "提前 2 分钟提醒" in message
    assert "| ID | 标题 | 开始时间 | 详情 |" in message
    assert (
        "| 26042802 | 下载DJ | 04-28 18:15 | 下载抖音热歌DJ音频 |"
        in message
    )
    assert "状态" not in message


def test_notification_task_table_uses_slot_label(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=_FakeLLM())

    message = agent._format_notification_task_table(
        [
            {
                "id": "26053108",
                "title": "买菜",
                "scheduled_at": "2026-05-31T14:00:00",
                "detail": "青菜",
                "time_kind": "slot",
                "time_slot": "afternoon",
            }
        ]
    )

    assert "| 26053108 | 买菜 | 05-31 下午 | 青菜 |" in message
    assert "05-31 14:00" not in message


def test_slot_task_reminder_notification_uses_heading_and_table(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=_FakeLLM())

    message = agent._format_notification(
        {
            "type": "slot_task_reminder",
            "data": {
                "business_day": "2026-05-31",
                "time_slot": "afternoon",
                "tasks": [
                    {
                        "id": "26053108",
                        "title": "买菜",
                        "scheduled_at": "2026-05-31T14:00:00",
                        "detail": "青菜",
                        "time_kind": "slot",
                        "time_slot": "afternoon",
                    }
                ],
            },
        }
    )

    assert message.startswith("## 下午任务提醒")
    assert "| 26053108 | 买菜 | 05-31 下午 | 青菜 |" in message
    assert "优先级" not in message


def test_morning_agenda_notification_uses_today_task_table(tmp_path):
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
                    }
                ],
            },
        }
    )

    assert message.startswith("## 今日任务\n")
    assert "【早报】" not in message
    assert "业务日:" not in message
    assert "时间:" not in message
    assert "今日任务:" not in message
    assert "今日任务：" not in message
    assert "未来任务：" not in message
    assert message.count("| ID | 标题 | 开始时间 | 详情 |") == 1
    assert "| 26042801 | 买草帽 | 04-28 21:30 | 商店购买 |" in message
    assert "状态" not in message
    assert "优先级" not in message
    assert "- ➖" not in message


def test_evening_agenda_notification_uses_tomorrow_task_table(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=_FakeLLM())

    message = agent._format_notification(
        {
            "type": "evening_agenda",
            "timestamp": "2026-05-31T23:00:00",
            "data": {
                "business_day": "2026-06-01",
                "tomorrow_tasks": [
                    {
                        "id": "26060101",
                        "title": "买菜",
                        "scheduled_at": "2026-06-01T14:00:00",
                        "detail": "",
                        "time_kind": "slot",
                        "time_slot": "afternoon",
                    }
                ],
            },
        }
    )

    assert message.startswith("## 明日任务\n")
    assert "【晚报】" not in message
    assert "业务日:" not in message
    assert "时间:" not in message
    assert "明日任务:" not in message
    assert "明日任务：" not in message
    assert "| 26060101 | 买菜 | 06-01 下午 |  |" in message


def test_noon_agenda_notification_uses_today_task_table(tmp_path):
    matrix = _FakeMatrixClient()
    media_store = _FakeMediaStore()
    agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=_FakeLLM())

    message = agent._format_notification(
        {
            "type": "noon_agenda",
            "timestamp": "2026-06-02T12:00:00",
            "data": {
                "business_day": "2026-06-02",
                "today_tasks": [
                    {
                        "id": "26060201",
                        "title": "买菜",
                        "scheduled_at": "2026-06-02T14:00:00",
                        "detail": "青菜",
                        "time_kind": "slot",
                        "time_slot": "afternoon",
                    }
                ],
            },
        }
    )

    assert message.startswith("## 今日任务\n")
    assert "【午报】" not in message
    assert "业务日:" not in message
    assert "时间:" not in message
    assert "| 26060201 | 买菜 | 06-02 下午 | 青菜 |" in message


def test_flush_notifications_marks_matrix_message_as_notification(tmp_path):
    async def run_once():
        matrix = _FakeMatrixClient()
        media_store = _FakeMediaStore()
        agent = TodoAgent(_config(tmp_path), matrix, media_store, llm=_FakeLLM())
        sink = get_notification_sink()
        sink.drain()
        sink.publish(
            {
                "type": "task_reminder",
                "data": {
                    "task": {
                        "id": "26053101",
                        "title": "买菜",
                        "scheduled_at": "2026-05-31T18:00:00",
                        "minutes_before": 5,
                    }
                },
            }
        )
        task = asyncio.create_task(agent._flush_notifications())
        await asyncio.sleep(0.05)
        agent._stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return matrix

    matrix = asyncio.run(run_once())

    assert matrix.sent_messages
    assert matrix.sent_message_extras == [{"com.talk.kind": "notification"}]
