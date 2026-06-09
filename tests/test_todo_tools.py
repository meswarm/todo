import asyncio
from datetime import date, datetime, time

from src.models import (
    Recurrence,
    RecurrencePattern,
    RecurrenceTemplate,
    Task,
    TimeKind,
    TimeSlot,
)
import src.tools.todo_tools as todo_tools
from src.tools.todo_tools import build_todo_tools


def test_build_todo_tools_exposes_core_operations():
    names = sorted(tool.definition.name for tool in build_todo_tools())

    assert "create_task" in names
    assert "get_task" in names
    assert "list_tasks" not in names
    assert "search_tasks" in names
    assert "update_task" in names
    assert "complete_task" not in names
    assert "delete_task" in names
    assert "get_agenda" not in names
    assert "create_recurrence" in names
    assert "update_recurrence" in names
    assert "list_recurrences" in names


def test_create_task_schema_exposes_simplified_fields():
    create_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "create_task")
    properties = create_tool.definition.parameters["properties"]

    assert "scheduled_at" in properties
    assert "detail" in properties
    assert "time_kind" in properties
    assert "time_slot" in properties
    assert "status" not in properties
    assert "difficulty" not in properties
    assert "time_mode" not in properties
    assert "urgency" not in properties
    assert "deadline" not in properties


def test_create_task_normalizes_short_month_day_datetime():
    create_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "create_task")
    task_service = create_tool._handler.__globals__["task_service"]
    original_create_task = task_service.create_task
    captured = {}

    def fake_create_task(payload):
        captured["scheduled_at"] = payload.scheduled_at
        return Task(id="26042899", title=payload.title, scheduled_at=payload.scheduled_at)

    task_service.create_task = fake_create_task

    try:
        result = asyncio.run(
            create_tool.execute(
                {
                    "title": "开会",
                    "scheduled_at": "04-28 19:27",
                }
            )
        )
    finally:
        task_service.create_task = original_create_task

    assert result["scheduled_at"].startswith(f"{datetime.now().year}-04-28T19:27:00")
    assert captured["scheduled_at"] == datetime(datetime.now().year, 4, 28, 19, 27)


def test_create_task_accepts_slot_time_fields():
    create_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "create_task")
    task_service = create_tool._handler.__globals__["task_service"]
    original_create_task = task_service.create_task
    captured = {}

    def fake_create_task(payload):
        captured["time_kind"] = payload.time_kind
        captured["time_slot"] = payload.time_slot
        return Task(
            id="26053108",
            title=payload.title,
            scheduled_at=payload.scheduled_at,
            detail=payload.detail,
            time_kind=payload.time_kind,
            time_slot=payload.time_slot,
        )

    task_service.create_task = fake_create_task

    try:
        result = asyncio.run(
            create_tool.execute(
                {
                    "title": "买菜",
                    "scheduled_at": "2026-05-31T14:00:00",
                    "time_kind": "slot",
                    "time_slot": "afternoon",
                }
            )
        )
    finally:
        task_service.create_task = original_create_task

    assert captured["time_kind"] == TimeKind.SLOT
    assert captured["time_slot"] == TimeSlot.AFTERNOON
    assert "| 26053108 | 买菜 | 05-31 下午 |  |" in result["task_markdown"]


def test_create_task_normalizes_slot_task_to_configured_anchor(monkeypatch):
    monkeypatch.setattr(
        todo_tools,
        "SLOT_REMINDER_TIMES",
        {"morning": time(7, 30), "afternoon": time(13, 45), "evening": time(19, 15)},
    )
    create_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "create_task")
    task_service = create_tool._handler.__globals__["task_service"]
    original_create_task = task_service.create_task
    captured = {}

    def fake_create_task(payload):
        captured["scheduled_at"] = payload.scheduled_at
        return Task(
            id="26053109",
            title=payload.title,
            scheduled_at=payload.scheduled_at,
            time_kind=payload.time_kind,
            time_slot=payload.time_slot,
        )

    task_service.create_task = fake_create_task

    try:
        asyncio.run(
            create_tool.execute(
                {
                    "title": "买菜",
                    "scheduled_at": "2026-05-31T12:12:00",
                    "time_kind": "slot",
                    "time_slot": "afternoon",
                }
            )
        )
    finally:
        task_service.create_task = original_create_task

    assert captured["scheduled_at"] == datetime(2026, 5, 31, 13, 45)


def test_create_task_returns_only_created_task_markdown():
    create_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "create_task")
    task_service = create_tool._handler.__globals__["task_service"]
    original_create_task = task_service.create_task

    def fake_create_task(payload):
        return Task(
            id="26053104",
            title=payload.title,
            scheduled_at=payload.scheduled_at,
            detail=payload.detail,
        )

    task_service.create_task = fake_create_task

    try:
        result = asyncio.run(
            create_tool.execute(
                {
                    "title": "打篮球",
                    "scheduled_at": "2026-05-31T17:26:00",
                    "detail": "带水",
                }
            )
        )
    finally:
        task_service.create_task = original_create_task

    assert result["task_markdown"] == (
        "| ID | 标题 | 开始时间 | 详情 |\n"
        "|---|---|---|---|\n"
        "| 26053104 | 打篮球 | 05-31 17:26 | 带水 |"
    )
    assert "26053101" not in result["task_markdown"]


def test_update_task_returns_only_updated_task_markdown():
    update_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "update_task")
    task_service = update_tool._handler.__globals__["task_service"]
    original_update_task = task_service.update_task

    def fake_update_task(task_id, payload):
        return Task(
            id=task_id,
            title=payload.title,
            scheduled_at=payload.scheduled_at,
            detail=payload.detail,
        )

    task_service.update_task = fake_update_task

    try:
        result = asyncio.run(
            update_tool.execute(
                {
                    "task_id": "26053104",
                    "title": "打篮球",
                    "scheduled_at": "2026-05-31T18:00:00",
                    "detail": "改到室内场",
                }
            )
        )
    finally:
        task_service.update_task = original_update_task

    assert result["task_markdown"] == (
        "| ID | 标题 | 开始时间 | 详情 |\n"
        "|---|---|---|---|\n"
        "| 26053104 | 打篮球 | 05-31 18:00 | 改到室内场 |"
    )
    assert "26053101" not in result["task_markdown"]


def test_delete_task_returns_status_without_current_task_list(monkeypatch):
    delete_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "delete_task")
    task_service = delete_tool._handler.__globals__["task_service"]

    monkeypatch.setattr(task_service, "get_task", lambda task_id: None)
    monkeypatch.setattr(task_service, "delete_task", lambda task_id: True)

    result = asyncio.run(delete_tool.execute({"task_id": "26053104"}))

    assert result == {
        "deleted": True,
        "task_id": "26053104",
        "message": "已删除任务 `26053104`",
    }
    assert "current_business_day_tasks_markdown" not in result


def test_build_day_agenda_does_not_project_skipped_recurrence(monkeypatch):
    recurrence = Recurrence(
        id="rec_20260428_001",
        title="每日铲屎喂粮",
        pattern=RecurrencePattern.DAILY,
        time_of_day="08:00",
        start_date=date(2026, 4, 28),
        skipped_dates=[date(2026, 6, 3)],
        template=RecurrenceTemplate(title="每日铲屎喂粮", detail="每天记得清理猫砂盆。"),
    )

    monkeypatch.setattr(todo_tools.task_service.task_store, "load_all", lambda: [])
    monkeypatch.setattr(todo_tools, "list_recurrences", lambda enabled_only=False: [recurrence])

    result = todo_tools.build_day_agenda(date(2026, 6, 3))

    assert result["tasks"] == []


def test_update_recurrence_updates_rule_without_touching_generated_tasks(monkeypatch):
    update_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "update_recurrence")
    captured = {}

    def fake_update_recurrence(recurrence_id, payload):
        captured["recurrence_id"] = recurrence_id
        captured["payload"] = payload
        return Recurrence(
            id=recurrence_id,
            title=payload.title or "每日铲屎喂粮",
            pattern=payload.pattern or RecurrencePattern.DAILY,
            time_of_day=payload.time_of_day or "08:00",
            start_date=payload.start_date or date(2026, 4, 28),
            last_generated_for=date(2026, 5, 31),
            template=RecurrenceTemplate(
                title=payload.template_title or "每日铲屎喂粮",
                detail=payload.detail or "每天记得清理猫砂盆并补充猫粮。",
            ),
        )

    monkeypatch.setattr(todo_tools, "update_recurrence", fake_update_recurrence)

    result = asyncio.run(
        update_tool.execute(
            {
                "recurrence_id": "rec_20260428_001",
                "time_of_day": "09:30",
                "template_title": "喂猫",
                "detail": "上午处理",
            }
        )
    )

    assert captured["recurrence_id"] == "rec_20260428_001"
    assert captured["payload"].time_of_day == "09:30"
    assert captured["payload"].template_title == "喂猫"
    assert captured["payload"].detail == "上午处理"
    assert result["id"] == "rec_20260428_001"
    assert result["time_of_day"] == "09:30"
    assert result["last_generated_for"] == "2026-05-31"


def test_update_recurrence_accepts_slot_anchor_time(monkeypatch):
    monkeypatch.setattr(
        todo_tools,
        "SLOT_REMINDER_TIMES",
        {"morning": time(7, 30), "afternoon": time(13, 45), "evening": time(19, 15)},
    )
    update_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "update_recurrence")
    captured = {}

    def fake_update_recurrence(recurrence_id, payload):
        captured["payload"] = payload
        return Recurrence(
            id=recurrence_id,
            title="每日铲屎喂粮",
            pattern=RecurrencePattern.DAILY,
            time_of_day=payload.time_of_day,
            time_slot=payload.time_slot,
            start_date=date(2026, 4, 28),
            template=RecurrenceTemplate(title="每日铲屎喂粮"),
        )

    monkeypatch.setattr(todo_tools, "update_recurrence", fake_update_recurrence)

    result = asyncio.run(
        update_tool.execute(
            {
                "recurrence_id": "rec_20260428_001",
                "time_slot": "morning",
            }
        )
    )

    assert captured["payload"].time_of_day == "07:30"
    assert captured["payload"].time_slot == TimeSlot.MORNING
    assert result["time_of_day"] == "07:30"
    assert result["time_slot"] == "morning"
