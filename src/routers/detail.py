"""任务详情 Markdown 文档 API"""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from src.services import task_service
import src.config as config

router = APIRouter(prefix="/tasks/{task_id}/detail", tags=["detail"])


class DetailUpdate(BaseModel):
    content: str


@router.put("")
async def update_detail(task_id: str, data: DetailUpdate):
    task = task_service.task_store.find_by_id(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    docs_dir = config.DOCS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_path = docs_dir / f"{task_id}.md"
    doc_path.write_text(data.content, encoding="utf-8")
    task.detail_doc = str(doc_path)
    task.updated_at = datetime.now()
    task_service.task_store.update(task_id, task)
    return {"detail_doc": str(doc_path)}


@router.get("", response_class=PlainTextResponse)
async def get_detail(task_id: str):
    task = task_service.task_store.find_by_id(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if not task.detail_doc:
        raise HTTPException(404, "No detail document")
    doc_path = Path(task.detail_doc)
    if not doc_path.exists():
        raise HTTPException(404, "Detail document file not found")
    return doc_path.read_text(encoding="utf-8")
