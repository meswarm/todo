"""搜索 API"""
from typing import Optional

from fastapi import APIRouter, Query

from src.services import task_service

router = APIRouter(prefix="/tasks/search", tags=["search"])


def _match(task_dict: dict, query: str) -> bool:
    q = query.lower()
    title = (task_dict.get("title") or "").lower()
    desc = (task_dict.get("description") or "").lower()
    notes_text = " ".join(
        (n.get("content") or "") for n in task_dict.get("notes", [])
    ).lower()
    tags_text = " ".join(task_dict.get("tags", [])).lower()
    return q in title or q in desc or q in notes_text or q in tags_text


@router.get("")
async def search_tasks(
    q: str = Query(..., min_length=1),
    scope: Optional[str] = "all",
):
    results = []
    if scope in ("all", "active"):
        for t in task_service.task_store.load_all():
            td = t.model_dump(mode="json")
            if _match(td, q):
                td["_source"] = "active"
                results.append(td)
    if scope in ("all", "history"):
        for t in task_service.history_store.load_all():
            td = t.model_dump(mode="json")
            if _match(td, q):
                td["_source"] = "history"
                results.append(td)
    return {"query": q, "count": len(results), "results": results}
