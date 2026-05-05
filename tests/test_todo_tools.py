import asyncio
from datetime import date, datetime

import src.tools.todo_tools as todo_tools
from src.models import (
    Recurrence,
    RecurrencePattern,
    RecurrenceTemplate,
    Task,
)
from src.tools.todo_tools import build_todo_tools


def test_build_todo_tools_exposes_core_operations():
    names = sorted(tool.definition.name for tool in build_todo_tools())

    assert "create_task" in names
    assert "get_task" in names
    assert "list_tasks" in names
    assert "search_tasks" in names
    assert "update_task" in names
    assert "complete_task" in names
    assert "delete_task" in names
    assert "get_agenda" in names
    assert "create_recurrence" in names
    assert "list_recurrences" in names


def test_get_agenda_accepts_iso_datetimes(monkeypatch):
    agenda_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "get_agenda")
    task_service = agenda_tool._handler.__globals__["task_service"]
    original_load_all = task_service.task_store.load_all
    task_service.task_store.load_all = lambda: []
    monkeypatch.setattr(todo_tools, "list_recurrences", lambda enabled_only=False: [])

    try:
        result = asyncio.run(
            agenda_tool.execute(
                {
                    "from": "2026-04-27T21:00:00",
                    "to": "2026-04-27T21:00:00",
                }
            )
        )
    finally:
        task_service.task_store.load_all = original_load_all

    assert result["range"] == {"start": "2026-04-27", "end": "2026-04-27"}


def test_get_agenda_includes_projected_recurring_tasks_for_tomorrow(monkeypatch):
    agenda_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "get_agenda")
    task_service = agenda_tool._handler.__globals__["task_service"]
    recurrences = [
        Recurrence(
            id="rec_20260428_001",
            title="每日铲屎喂粮",
            pattern=RecurrencePattern.DAILY,
            time_of_day="08:00",
            start_date=date(2026, 4, 29),
            last_generated_for=date(2026, 5, 5),
            template=RecurrenceTemplate(
                title="每日铲屎喂粮",
                detail="清理猫砂盆并补充猫粮。",
            ),
        )
    ]

    monkeypatch.setattr(todo_tools, "business_date", lambda: date(2026, 5, 5))
    monkeypatch.setattr(task_service.task_store, "load_all", lambda: [])
    monkeypatch.setattr(todo_tools, "list_recurrences", lambda enabled_only=False: recurrences)

    result = asyncio.run(agenda_tool.execute({"range": "tomorrow"}))

    assert result["range"] == {"start": "2026-05-06", "end": "2026-05-06"}
    assert result["summary"]["total"] == 1
    assert result["tasks"][0]["title"] == "每日铲屎喂粮"
    assert result["tasks"][0]["scheduled_at"] == "2026-05-06T08:00:00"
    assert result["tasks"][0]["recurrence_id"] == "rec_20260428_001"


def test_create_task_schema_exposes_simplified_fields():
    create_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "create_task")
    properties = create_tool.definition.parameters["properties"]

    assert "scheduled_at" in properties
    assert "detail" in properties
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


def test_complete_task_returns_current_business_day_table_with_completed_tasks(monkeypatch):
    complete_tool = next(tool for tool in build_todo_tools() if tool.definition.name == "complete_task")
    task_service = complete_tool._handler.__globals__["task_service"]
    original_complete_task = task_service.complete_task
    original_load_all = task_service.task_store.load_all

    completed = Task(
        id="26042803",
        title="买方便面",
        scheduled_at=datetime(2026, 4, 28, 22, 0),
        completed_at=datetime(2026, 4, 28, 22, 5),
    )
    incomplete = Task(
        id="26042804",
        title="喂猫",
        scheduled_at=datetime(2026, 4, 28, 19, 27),
    )

    task_service.complete_task = lambda task_id, payload: completed
    task_service.task_store.load_all = lambda: [completed, incomplete]
    monkeypatch.setattr(todo_tools, "business_date", lambda: date(2026, 4, 28))

    try:
        result = asyncio.run(
            complete_tool.execute(
                {
                    "task_id": "26042803",
                    "completion_summary": "已完成",
                }
            )
        )
    finally:
        task_service.complete_task = original_complete_task
        task_service.task_store.load_all = original_load_all

    table = result["current_business_day_tasks_markdown"]
    assert "| ID | 标题 | 开始时间 | 详情 | 完成总结 |" in table
    assert "| 26042803 | 买方便面 | 04-28 22:00 |  |  |" in table
    assert "| 26042804 | 喂猫 | 04-28 19:27 |  |  |" in table
    assert "状态" not in table
    assert "优先级" not in table
