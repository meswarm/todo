"""备注 API"""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services import task_service
from src.models import Note

router = APIRouter(prefix="/tasks/{task_id}/notes", tags=["notes"])


class NoteCreate(BaseModel):
    content: str


@router.post("", status_code=201)
async def add_note(task_id: str, data: NoteCreate):
    task = task_service.task_store.find_by_id(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    note = Note(time=datetime.now(), content=data.content)
    task.notes.append(note)
    task.updated_at = datetime.now()
    task_service.task_store.update(task_id, task)
    return note


@router.get("")
async def get_notes(task_id: str):
    task = task_service.task_store.find_by_id(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task.notes
