"""子任务 API"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services import task_service
from src.utils.id_gen import generate_sub_id
from src.models import SubTask, TaskStatus

router = APIRouter(prefix="/tasks/{task_id}/subtasks", tags=["subtasks"])


class SubTaskCreate(BaseModel):
    title: str


class SubTaskUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[TaskStatus] = None


@router.post("", status_code=201)
async def add_subtask(task_id: str, data: SubTaskCreate):
    task = task_service.task_store.find_by_id(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    sub_id = generate_sub_id([s.id for s in task.subtasks])
    sub = SubTask(id=sub_id, title=data.title)
    task.subtasks.append(sub)
    task.updated_at = datetime.now()
    task_service.task_store.update(task_id, task)
    return sub


@router.patch("/{sub_id}")
async def update_subtask(task_id: str, sub_id: str, data: SubTaskUpdate):
    task = task_service.task_store.find_by_id(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    for sub in task.subtasks:
        if sub.id == sub_id:
            if data.title is not None:
                sub.title = data.title
            if data.status is not None:
                sub.status = data.status
            task.updated_at = datetime.now()
            task_service.task_store.update(task_id, task)
            return sub
    raise HTTPException(404, "Subtask not found")


@router.delete("/{sub_id}")
async def delete_subtask(task_id: str, sub_id: str):
    task = task_service.task_store.find_by_id(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    new_subs = [s for s in task.subtasks if s.id != sub_id]
    if len(new_subs) == len(task.subtasks):
        raise HTTPException(404, "Subtask not found")
    task.subtasks = new_subs
    task.updated_at = datetime.now()
    task_service.task_store.update(task_id, task)
    return {"detail": "Deleted"}
