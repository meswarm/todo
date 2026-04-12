"""任务业务逻辑"""
from datetime import datetime

from src.models import (
    Task, TaskCreate, TaskUpdate, TaskStatus,
    StatusChange, Completion,
)
from src.storage import JsonStore
from src.config import TASKS_FILE, HISTORY_FILE
from src.utils.id_gen import generate_task_id

# 全局 store 实例
task_store = JsonStore(TASKS_FILE, Task)
history_store = JsonStore(HISTORY_FILE, Task)


def create_task(data: TaskCreate) -> Task:
    task = Task(
        id=generate_task_id(),
        **data.model_dump(),
    )
    task_store.add(task)
    return task


def get_tasks(
    status: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    is_overdue: bool | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[Task]:
    tasks = task_store.load_all()
    if status:
        tasks = [t for t in tasks if t.status == status]
    if category:
        tasks = [t for t in tasks if t.category == category]
    if tags:
        tasks = [t for t in tasks if any(tag in t.tags for tag in tags)]
    if is_overdue is not None:
        tasks = [t for t in tasks if t.is_overdue == is_overdue]
    if from_date:
        fd = datetime.fromisoformat(from_date)
        tasks = [t for t in tasks if t.deadline and t.deadline >= fd]
    if to_date:
        td = datetime.fromisoformat(to_date)
        tasks = [t for t in tasks if t.deadline and t.deadline <= td]
    return tasks


def get_task(task_id: str) -> Task | None:
    return task_store.find_by_id(task_id)


def update_task(task_id: str, data: TaskUpdate) -> Task | None:
    task = task_store.find_by_id(task_id)
    if not task:
        return None
    update_data = data.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(task, key, value)
    task.updated_at = datetime.now()
    task_store.update(task_id, task)
    return task


def delete_task(task_id: str) -> bool:
    return task_store.delete(task_id)


def change_status(task_id: str, data: StatusChange) -> Task | None:
    task = task_store.find_by_id(task_id)
    if not task:
        return None
    # 状态流转校验
    valid_transitions = {
        TaskStatus.PENDING: [TaskStatus.IN_PROGRESS, TaskStatus.ABANDONED],
        TaskStatus.IN_PROGRESS: [TaskStatus.COMPLETED, TaskStatus.ABANDONED],
    }
    allowed = valid_transitions.get(task.status, [])
    if data.status not in allowed:
        raise ValueError(
            f"Cannot change from {task.status} to {data.status}"
        )
    task.status = data.status
    task.updated_at = datetime.now()

    if data.status in (TaskStatus.COMPLETED, TaskStatus.ABANDONED):
        task.completion = Completion(
            completed_at=datetime.now(),
            actual_minutes=data.actual_minutes,
            summary=data.summary,
        )
        # 迁移到历史
        task_store.update(task_id, task)
        task_store.move_to(task_id, history_store)
    else:
        task_store.update(task_id, task)
    return task
