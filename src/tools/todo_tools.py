"""Todo builtin tools exposed to the LLM."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from src.models import (
    Recurrence,
    RecurrenceCreate,
    RecurrencePattern,
    RecurrenceTemplate,
    Task,
    TaskComplete,
    TaskCreate,
    TaskUpdate,
)
from src.context import _format_tasks
from src.scheduler.recurrence_gen import create_recurrence, list_recurrences
from src.services import task_service
from src.services.agenda_service import get_tasks_in_range, sort_tasks_for_agenda
from src.services.business_day import business_date
from src.tools.base import ToolDefinition
from src.tools.builtin import BuiltinTool


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def _task_to_dict(task: Task) -> dict[str, Any]:
    return task.model_dump(mode="json")


def _match_task(task: Task, query: str) -> bool:
    normalized = query.lower()
    haystack = " ".join(
        [
            task.title,
            task.detail or "",
            task.completion_summary or "",
        ]
    ).lower()
    return normalized in haystack


def _parse_date(value: str) -> date:
    normalized = value.strip()
    if "T" in normalized:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
    return date.fromisoformat(normalized)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


_SHORT_MONTH_DAY_DATETIME_RE = re.compile(
    r"^(?P<month>\d{1,2})-(?P<day>\d{1,2})[T ](?P<time>\d{1,2}:\d{2}(?::\d{2})?)$"
)


def _normalize_datetime_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if not normalized:
        return value
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        pass

    match = _SHORT_MONTH_DAY_DATETIME_RE.match(normalized)
    if not match:
        return value

    time_part = match.group("time")
    if len(time_part.split(":")) == 2:
        time_part = f"{time_part}:00"
    return datetime.fromisoformat(
        f"{datetime.now().year}-{int(match.group('month')):02d}-"
        f"{int(match.group('day')):02d}T{time_part}"
    )


def _normalize_datetime_fields(args: dict[str, Any], *field_names: str) -> dict[str, Any]:
    normalized = dict(args)
    for field_name in field_names:
        if field_name in normalized:
            normalized[field_name] = _normalize_datetime_value(normalized[field_name])
    return normalized


def _recurrence_occurs_on(recurrence: Recurrence, day: date) -> bool:
    if not recurrence.enabled:
        return False
    if day < recurrence.start_date:
        return False
    if recurrence.end_date and day > recurrence.end_date:
        return False
    if recurrence.pattern == RecurrencePattern.DAILY:
        return True
    if recurrence.pattern == RecurrencePattern.WEEKLY:
        return day.isoweekday() in (recurrence.week_days or [])
    if recurrence.pattern == RecurrencePattern.MONTHLY:
        return day.day == recurrence.month_day
    if recurrence.pattern == RecurrencePattern.INTERVAL:
        interval = recurrence.interval_days or 1
        return (day - recurrence.start_date).days % interval == 0
    return False


def _project_recurring_tasks(start: date, end: date, existing_tasks: list[Task]) -> list[Task]:
    existing_pairs = {
        (task.recurrence_id, business_date(task.scheduled_at))
        for task in existing_tasks
        if task.recurrence_id
    }
    projected: list[Task] = []
    recurrences = list_recurrences(enabled_only=True)
    day = start
    while day <= end:
        for recurrence in recurrences:
            pair = (recurrence.id, day)
            if pair in existing_pairs or not _recurrence_occurs_on(recurrence, day):
                continue
            hour, minute = map(int, recurrence.time_of_day.split(":"))
            template = recurrence.template
            projected.append(
                Task(
                    id="",
                    title=template.title,
                    scheduled_at=datetime.combine(day, time(hour=hour, minute=minute)),
                    detail=template.detail,
                    recurrence_id=recurrence.id,
                )
            )
        day += timedelta(days=1)
    return projected


def _build_agenda(
    range_name: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    all_tasks = task_service.task_store.load_all()
    today = business_date()

    if from_date and to_date:
        start = _parse_date(from_date)
        end = _parse_date(to_date)
    elif range_name == "today":
        start = end = today
    elif range_name == "tomorrow":
        start = end = today + timedelta(days=1)
    elif range_name and range_name.endswith("d"):
        start = today
        end = today + timedelta(days=int(range_name[:-1]))
    else:
        start = end = today

    range_tasks = get_tasks_in_range(all_tasks, start, end)
    tasks = sort_tasks_for_agenda(
        range_tasks + _project_recurring_tasks(start, end, all_tasks)
    )
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "tasks": [_task_to_dict(task) for task in tasks],
        "summary": {"total": len(tasks)},
    }


def _current_business_day_tasks_markdown() -> str:
    today = business_date()
    tasks = sort_tasks_for_agenda(
        get_tasks_in_range(task_service.task_store.load_all(), today, today)
    )
    return _format_tasks(tasks)


def _with_current_business_day_table(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "current_business_day_tasks_markdown": _current_business_day_tasks_markdown(),
    }


def build_todo_tools() -> list[BuiltinTool]:
    async def create_task_tool(args: dict[str, Any]) -> dict[str, Any]:
        task = task_service.create_task(
            TaskCreate(**_normalize_datetime_fields(args, "scheduled_at"))
        )
        return _with_current_business_day_table(_task_to_dict(task))

    async def get_task(args: dict[str, Any]) -> dict[str, Any]:
        task = task_service.get_task(args["task_id"])
        if not task:
            return {"error": "Task not found"}
        return _task_to_dict(task)

    async def list_tasks_tool(args: dict[str, Any]) -> list[dict[str, Any]]:
        start = _parse_date(args["from_date"]) if args.get("from_date") else None
        end = _parse_date(args["to_date"]) if args.get("to_date") else None
        tasks = task_service.list_tasks(
            start=start,
            end=end,
            include_recurring=args.get("include_recurring", True),
        )
        return [_task_to_dict(task) for task in sort_tasks_for_agenda(tasks)]

    async def search_tasks_tool(args: dict[str, Any]) -> dict[str, Any]:
        query = args["query"]
        scope = args.get("scope", "all")
        if scope not in {"all", "active", "history"}:
            raise ValueError(f"Invalid scope: {scope}")

        results: list[dict[str, Any]] = []
        if scope in {"all", "active"}:
            for task in task_service.task_store.load_all():
                if _match_task(task, query):
                    payload = _task_to_dict(task)
                    payload["_source"] = "active"
                    results.append(payload)
        if scope in {"all", "history"}:
            for task in task_service.history_store.load_all():
                if _match_task(task, query):
                    payload = _task_to_dict(task)
                    payload["_source"] = "history"
                    results.append(payload)
        return {"query": query, "count": len(results), "results": results}

    async def update_task_tool(args: dict[str, Any]) -> dict[str, Any]:
        task = task_service.update_task(
            args["task_id"],
            TaskUpdate(**_normalize_datetime_fields(args, "scheduled_at", "completed_at")),
        )
        if not task:
            return {"error": "Task not found"}
        return _with_current_business_day_table(_task_to_dict(task))

    async def complete_task_tool(args: dict[str, Any]) -> dict[str, Any]:
        task = task_service.complete_task(
            args["task_id"],
            TaskComplete(**_normalize_datetime_fields(args, "completed_at")),
        )
        if not task:
            return {"error": "Task not found"}
        return _with_current_business_day_table(_task_to_dict(task))

    async def delete_task_tool(args: dict[str, Any]) -> dict[str, Any]:
        deleted = task_service.delete_task(args["task_id"])
        return _with_current_business_day_table(
            {"deleted": deleted, "task_id": args["task_id"]}
        )

    async def get_agenda_tool(args: dict[str, Any]) -> dict[str, Any]:
        return _build_agenda(
            range_name=args.get("range"),
            from_date=args.get("from"),
            to_date=args.get("to"),
        )

    async def create_recurrence_tool(args: dict[str, Any]) -> dict[str, Any]:
        payload = RecurrenceCreate(
            title=args["title"],
            pattern=args["pattern"],
            interval_days=args.get("interval_days"),
            week_days=args.get("week_days"),
            month_day=args.get("month_day"),
            time_of_day=args["time_of_day"],
            start_date=_parse_date(args["start_date"]),
            end_date=_parse_date(args["end_date"]) if args.get("end_date") else None,
            template=RecurrenceTemplate(
                title=args.get("template_title", args["title"]),
                detail=args.get("detail"),
            ),
        )
        recurrence = create_recurrence(payload)
        return recurrence.model_dump(mode="json")

    async def list_recurrences_tool(args: dict[str, Any]) -> list[dict[str, Any]]:
        enabled_only = bool(args.get("enabled_only", False))
        return [item.model_dump(mode="json") for item in list_recurrences(enabled_only)]

    return [
        BuiltinTool(
            ToolDefinition(
                name="create_task",
                description="Create a one-time task.",
                parameters=_schema(
                    {
                        "title": {"type": "string", "maxLength": 10},
                        "scheduled_at": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                    ["title", "scheduled_at"],
                ),
            ),
            create_task_tool,
        ),
        BuiltinTool(
            ToolDefinition(
                name="get_task",
                description="Get task details by id.",
                parameters=_schema({"task_id": {"type": "string"}}, ["task_id"]),
            ),
            get_task,
        ),
        BuiltinTool(
            ToolDefinition(
                name="list_tasks",
                description="List tasks by date range.",
                parameters=_schema(
                    {
                        "from_date": {"type": "string"},
                        "to_date": {"type": "string"},
                        "include_recurring": {"type": "boolean"},
                    },
                    [],
                ),
            ),
            list_tasks_tool,
        ),
        BuiltinTool(
            ToolDefinition(
                name="search_tasks",
                description="Search active or historical tasks by keyword.",
                parameters=_schema(
                    {
                        "query": {"type": "string"},
                        "scope": {"type": "string", "enum": ["all", "active", "history"]},
                    },
                    ["query"],
                ),
            ),
            search_tasks_tool,
        ),
        BuiltinTool(
            ToolDefinition(
                name="update_task",
                description="Update task fields before completion.",
                parameters=_schema(
                    {
                        "task_id": {"type": "string"},
                        "title": {"type": "string", "maxLength": 10},
                        "scheduled_at": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                    ["task_id"],
                ),
            ),
            update_task_tool,
        ),
        BuiltinTool(
            ToolDefinition(
                name="complete_task",
                description="Mark a task as completed and save completion notes.",
                parameters=_schema(
                    {
                        "task_id": {"type": "string"},
                        "completion_summary": {"type": "string"},
                        "completed_at": {"type": "string"},
                    },
                    ["task_id"],
                ),
            ),
            complete_task_tool,
        ),
        BuiltinTool(
            ToolDefinition(
                name="delete_task",
                description="Delete a task by id.",
                parameters=_schema({"task_id": {"type": "string"}}, ["task_id"]),
            ),
            delete_task_tool,
        ),
        BuiltinTool(
            ToolDefinition(
                name="get_agenda",
                description=(
                    "Get tasks and projected recurring occurrences for today, "
                    "tomorrow, or a custom date range."
                ),
                parameters=_schema(
                    {
                        "range": {"type": "string"},
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                    },
                    [],
                ),
            ),
            get_agenda_tool,
        ),
        BuiltinTool(
            ToolDefinition(
                name="create_recurrence",
                description="Create a recurring rule that generates a task instance each business day.",
                parameters=_schema(
                    {
                        "title": {"type": "string", "maxLength": 10},
                        "template_title": {"type": "string", "maxLength": 10},
                        "detail": {"type": "string"},
                        "pattern": {
                            "type": "string",
                            "enum": [pattern.value for pattern in RecurrencePattern],
                        },
                        "interval_days": {"type": "integer", "minimum": 1},
                        "week_days": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 7}},
                        "month_day": {"type": "integer", "minimum": 1, "maximum": 31},
                        "time_of_day": {"type": "string"},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                    },
                    ["title", "pattern", "time_of_day", "start_date"],
                ),
            ),
            create_recurrence_tool,
        ),
        BuiltinTool(
            ToolDefinition(
                name="list_recurrences",
                description="List recurring rules.",
                parameters=_schema({"enabled_only": {"type": "boolean"}}, []),
            ),
            list_recurrences_tool,
        ),
    ]
