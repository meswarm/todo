"""Helpers for business-day task filtering and ordering."""
from __future__ import annotations

from datetime import date

from src.models import Task
from src.services.business_day import business_date


def sort_tasks_for_agenda(tasks: list[Task]) -> list[Task]:
    """Sort tasks for human scanning by scheduled time."""
    return sorted(tasks, key=lambda task: task.scheduled_at)


def get_tasks_on_day(tasks: list[Task], day: date) -> list[Task]:
    """Filter tasks for one business day based on scheduled time."""
    return [task for task in tasks if business_date(task.scheduled_at) == day]
