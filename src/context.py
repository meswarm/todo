"""Dynamic context prompt helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from string import Formatter

from src.config import CONTEXT_CELL_MAX_CHARS
from src.models import Recurrence, RecurrencePattern, Task, TimeKind, TimeSlot
from src.scheduler.recurrence_gen import recurrence_store
from src.services import task_service
from src.services.agenda_service import get_tasks_on_day, sort_tasks_for_agenda
from src.services.business_day import business_date

MAX_CONTEXT_TASKS = 24
MAX_CONTEXT_RECURRENCES = 12
R2_LINK_RE = re.compile(r"r2://[^\s\]\)\}\"';:>]+")
WEEKDAY_NAMES = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}
TIME_SLOT_LABELS = {
    TimeSlot.MORNING: "上午",
    TimeSlot.AFTERNOON: "下午",
    TimeSlot.EVENING: "晚上",
}


@dataclass(frozen=True)
class RuntimeContext:
    current_time: str
    today: str
    today_tasks: str
    upcoming_tasks: str
    overdue_tasks: str
    recurring_tasks: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "current_time": self.current_time,
            "today": self.today,
            "today_tasks": self.today_tasks,
            "upcoming_tasks": self.upcoming_tasks,
            "overdue_tasks": self.overdue_tasks,
            "recurring_tasks": self.recurring_tasks,
        }


def build_context_prompt(context_values: dict[str, str | int | float | bool | None]) -> str:
    if not context_values:
        return ""
    lines = ["", "# Context"]
    for key, value in context_values.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def render_prompt_template(template: str, values: dict[str, str]) -> str:
    placeholders = {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    }
    render_values = {name: values.get(name, "") for name in placeholders}
    return template.format(**render_values)


def build_runtime_context(now: datetime | None = None) -> RuntimeContext:
    current = now or datetime.now()
    today = business_date(current)
    all_tasks = task_service.task_store.load_all()
    recurrences = recurrence_store.load_all()
    today_tasks = sort_tasks_for_agenda(get_tasks_on_day(all_tasks, today))
    future_tasks = sort_tasks_for_agenda(
        [
            task
            for task in all_tasks
            if business_date(task.scheduled_at) > today and task.recurrence_id is None
        ]
    )
    overdue_tasks = sort_tasks_for_agenda(
        [
            task
            for task in all_tasks
            if task.scheduled_at < current
        ]
    )
    return RuntimeContext(
        current_time=current.strftime("%Y-%m-%d %H:%M:%S"),
        today=today.isoformat(),
        today_tasks=_format_tasks(today_tasks),
        upcoming_tasks=_format_tasks(future_tasks),
        overdue_tasks=_format_tasks(overdue_tasks),
        recurring_tasks=_format_recurrences(recurrences),
    )


def _format_tasks(tasks: list[Task]) -> str:
    if not tasks:
        return "无"

    visible_tasks = tasks[:MAX_CONTEXT_TASKS]
    lines = [
        "| ID | 标题 | 开始时间 | 详情 |",
        "|---|---|---|---|",
    ]
    for task in visible_tasks:
        detail = _cell(task.detail)
        if task.recurrence_id:
            detail = f"{detail} 周期".strip()
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(task.id),
                    _cell(task.title),
                    task_time_cell(task),
                    detail,
                ]
            )
            + " |"
        )

    remaining = len(tasks) - MAX_CONTEXT_TASKS
    if remaining > 0:
        lines.append(f"\n另有 {remaining} 个任务未展开")
    return "\n".join(lines)


def task_time_cell(task: Task) -> str:
    if task.completed:
        return "✅"
    return format_task_time_label(task.scheduled_at, task.time_kind, task.time_slot)


def format_task_time_label(
    value: datetime,
    time_kind: TimeKind | str | None = TimeKind.EXACT,
    time_slot: TimeSlot | str | None = None,
) -> str:
    kind = TimeKind(time_kind or TimeKind.EXACT)
    slot = TimeSlot(time_slot) if time_slot else None
    date_part = _date_label(value)
    if kind == TimeKind.SLOT and slot:
        return f"{date_part} {TIME_SLOT_LABELS[slot]}"
    return f"{date_part} {value:%H:%M}"


def _date_label(value: datetime) -> str:
    if value.year != datetime.now().year:
        return value.strftime("%Y-%m-%d")
    return value.strftime("%m-%d")


def _format_recurrences(recurrences: list[Recurrence]) -> str:
    active = [rec for rec in recurrences if rec.enabled]
    if not active:
        return "无"
    lines = [
        "| ID | 标题 | 周期 | 模板任务 | 详情 |",
        "|---|---|---|---|---|",
    ]
    for rec in active[:MAX_CONTEXT_RECURRENCES]:
        lines.append(_format_recurrence_row(rec))
    remaining = len(active) - MAX_CONTEXT_RECURRENCES
    if remaining > 0:
        lines.append(f"\n另有 {remaining} 条周期规则未展开")
    return "\n".join(lines)


def _format_recurrence(rec: Recurrence) -> str:
    return _format_recurrence_row(rec).strip("| ")


def _format_recurrence_row(rec: Recurrence) -> str:
    time_label = TIME_SLOT_LABELS.get(rec.time_slot, rec.time_of_day)
    cadence: str
    if rec.pattern == RecurrencePattern.DAILY:
        cadence = f"每日 {time_label}"
    elif rec.pattern == RecurrencePattern.WEEKLY:
        days = "/".join(WEEKDAY_NAMES.get(day, str(day)) for day in (rec.week_days or []))
        cadence = f"每周{days or '?'} {time_label}"
    elif rec.pattern == RecurrencePattern.MONTHLY:
        cadence = f"每月{rec.month_day or '?'}日 {time_label}"
    else:
        cadence = f"每{rec.interval_days or 1}天 {time_label}"

    values = [
        _cell(rec.id),
        _cell(rec.title),
        _cell(cadence),
        _cell(rec.template.title),
        _cell(rec.template.detail or ""),
    ]
    return "| " + " | ".join(values) + " |"


def _cell(value: object) -> str:
    text = str(value or "").replace("\n", "<br>").replace("|", "\\|").strip()
    max_chars = max(CONTEXT_CELL_MAX_CHARS, 20)
    if len(text) > max_chars:
        return _truncate_cell(text, max_chars)
    return text


def _truncate_cell(text: str, max_chars: int) -> str:
    match = None
    for candidate in R2_LINK_RE.finditer(text):
        match = candidate
    if match and match.end() == len(text):
        suffix = match.group(0)
        if len(suffix) >= max_chars - 3:
            return suffix
        prefix_len = max_chars - len(suffix) - 3
        return f"{text[:prefix_len]}...{suffix}"
    return text[: max_chars - 3] + "..."
