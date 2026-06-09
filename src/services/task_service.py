"""Task service for the simplified task model."""
from __future__ import annotations

from datetime import datetime

from src.config import HISTORY_FILE, TASKS_FILE
from src.models import Task, TaskCreate, TaskUpdate
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


def update_task(task_id: str, data: TaskUpdate) -> Task | None:
    task = task_store.find_by_id(task_id)
    if not task:
        return None

    for key, value in data.model_dump(exclude_none=True).items():
        setattr(task, key, value)
    task_store.update(task_id, task)
    return task


def delete_task(task_id: str) -> bool:
    return task_store.delete(task_id)


def complete_task(task_id: str) -> Task | None:
    task = task_store.find_by_id(task_id)
    if not task:
        return None
    task.completed = True
    task_store.update(task_id, task)
    return task


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
