"""任务 CRUD API"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.models import TaskCreate, TaskUpdate, Task, StatusChange, Reminder
from src.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=Task, status_code=201)
async def create_task(data: TaskCreate):
    return task_service.create_task(data)


@router.get("", response_model=list[Task])
async def list_tasks(
    status: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    is_overdue: Optional[bool] = None,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    tag_list = tags.split(",") if tags else None
    return task_service.get_tasks(
        status=status, category=category, tags=tag_list,
        is_overdue=is_overdue, from_date=from_date, to_date=to_date,
    )


@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: str):
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=Task)
async def update_task(task_id: str, data: TaskUpdate):
    task = task_service.update_task(task_id, data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    if not task_service.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"detail": "Deleted"}


@router.patch("/{task_id}/status", response_model=Task)
async def change_status(task_id: str, data: StatusChange):
    try:
        task = task_service.change_status(task_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}/reminders")
async def set_reminders(task_id: str, reminders: list[Reminder]):
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.reminders = reminders
    task.updated_at = datetime.now()
    task_service.task_store.update(task_id, task)
    return {"reminders": [r.model_dump(mode="json") for r in task.reminders]}


@router.put("/{task_id}/dependencies")
async def set_dependencies(task_id: str, depends_on: list[str]):
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.depends_on = depends_on
    task.updated_at = datetime.now()
    task_service.task_store.update(task_id, task)
    return {"depends_on": task.depends_on}
