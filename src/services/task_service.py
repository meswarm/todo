"""Task service for the simplified task model."""
from __future__ import annotations

from datetime import date, datetime

from src.config import HISTORY_FILE, TASKS_FILE
from src.models import Task, TaskComplete, TaskCreate, TaskUpdate
from src.storage import JsonStore
from src.utils.id_gen import generate_task_id

task_store = JsonStore(TASKS_FILE, Task)
history_store = JsonStore(HISTORY_FILE, Task)


def create_task(data: TaskCreate) -> Task:
    existing_ids = [task.id for task in task_store.load_all() + history_store.load_all()]
    task = Task(
        id=generate_task_id(existing_ids),
        **data.model_dump(),
    )
    task_store.add(task)
    return task


def get_task(task_id: str) -> Task | None:
    task = task_store.find_by_id(task_id)
    if task:
        return task
    return history_store.find_by_id(task_id)


def list_tasks(
    start: date | datetime | None = None,
    end: date | datetime | None = None,
    include_recurring: bool = True,
) -> list[Task]:
    tasks = task_store.load_all()
    if start:
        start_dt = (
            datetime.combine(start, datetime.min.time())
            if isinstance(start, date) and not isinstance(start, datetime)
            else start
        )
        tasks = [task for task in tasks if task.scheduled_at >= start_dt]
    if end:
        end_dt = (
            datetime.combine(end, datetime.max.time())
            if isinstance(end, date) and not isinstance(end, datetime)
            else end
        )
        tasks = [task for task in tasks if task.scheduled_at <= end_dt]
    if not include_recurring:
        tasks = [task for task in tasks if task.recurrence_id is None]
    return sorted(tasks, key=lambda task: task.scheduled_at)


def update_task(task_id: str, data: TaskUpdate) -> Task | None:
    task = task_store.find_by_id(task_id)
    if not task:
        return None

    for key, value in data.model_dump(exclude_none=True).items():
        setattr(task, key, value)
    task_store.update(task_id, task)
    return task


def complete_task(task_id: str, data: TaskComplete) -> Task | None:
    task = task_store.find_by_id(task_id)
    if not task:
        return None

    task.completed_at = data.completed_at or datetime.now()
    task.completion_summary = data.completion_summary
    task_store.update(task_id, task)
    return task


def delete_task(task_id: str) -> bool:
    return task_store.delete(task_id)


def archive_before(cutoff: datetime) -> int:
    tasks = task_store.load_all()
    moved = 0
    remaining: list[Task] = []
    archived: list[Task] = []

    for task in tasks:
        if task.scheduled_at < cutoff:
            archived.append(task)
            moved += 1
        else:
            remaining.append(task)

    if moved:
        task_store.save_all(remaining)
        history = history_store.load_all()
        history_store.save_all(history + archived)
    return moved
