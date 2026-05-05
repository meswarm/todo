"""Helpers for business-day task filtering and ordering."""
from __future__ import annotations

from datetime import date, datetime

from src.models import Task
from src.services.business_day import business_date


def sort_tasks_for_agenda(tasks: list[Task]) -> list[Task]:
    """Sort tasks for human scanning: active first, then by scheduled time."""

    def sort_key(task: Task) -> tuple[int, datetime, datetime]:
        completed_rank = 1 if task.completed_at else 0
        completed_at = task.completed_at or datetime.max
        return (completed_rank, task.scheduled_at, completed_at)

    return sorted(tasks, key=sort_key)


def get_tasks_in_range(tasks: list[Task], start: date, end: date) -> list[Task]:
    """Filter tasks by business-date range based on scheduled time."""
    result: list[Task] = []
    for task in tasks:
        task_day = business_date(task.scheduled_at)
        if start <= task_day <= end:
            result.append(task)
    return result
