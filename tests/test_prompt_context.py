"""Prompt and context helper tests."""

from datetime import date, datetime

from src.context import (
    build_context_prompt,
    render_prompt_template,
    _format_recurrence,
    _format_tasks,
    _truncate_cell,
)
from src.models import Recurrence, RecurrencePattern, RecurrenceTemplate, Task


def test_build_context_prompt_contains_sections():
    prompt = build_context_prompt({"today": "2026-04-27", "agenda": "无任务"})
    assert "today: 2026-04-27" in prompt
    assert "agenda: 无任务" in prompt


def test_render_prompt_template_replaces_runtime_context():
    prompt = render_prompt_template(
        "现在是 {current_time}\n今天任务:\n{today_tasks}",
        {
            "current_time": "2026-04-27 19:50:00",
            "today_tasks": "- 开会",
        },
    )

    assert "2026-04-27 19:50:00" in prompt
    assert "- 开会" in prompt


def test_format_weekly_recurrence_is_compact():
    recurrence = Recurrence(
        id="rec_001",
        title="健身计划",
        template=RecurrenceTemplate(
            title="去健身房",
        ),
        pattern=RecurrencePattern.WEEKLY,
        week_days=[1, 3, 5],
        time_of_day="18:00",
        start_date=date(2026, 4, 1),
    )

    summary = _format_recurrence(recurrence)

    assert "每周周一/周三/周五 18:00" in summary
    assert "去健身房" in summary
    assert "优先级" not in summary


def test_format_tasks_outputs_markdown_table():
    task = Task(
        id="task_001",
        title="买电脑",
        scheduled_at=datetime(2026, 4, 28, 15, 0),
        detail="去店里看看",
    )

    table = _format_tasks([task])

    assert "| ID | 标题 | 开始时间 | 详情 | 完成总结 |" in table
    assert "| task_001 | 买电脑 | 04-28 15:00 | 去店里看看 |  |" in table
    assert "状态" not in table
    assert "优先级" not in table


def test_truncate_cell_preserves_trailing_r2_link():
    link = "r2://linux-storage/todo/imgs/1777303364542-1000013464.jpg"
    text = "这是很长的一段任务详情说明，需要压缩普通描述，但末尾链接必须完整保留 " + link

    truncated = _truncate_cell(text, 80)

    assert truncated.endswith(link)
    assert "..." in truncated
