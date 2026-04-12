"""日程视图 API"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from src.services import task_service
from src.services.agenda_service import sort_tasks_for_agenda, get_tasks_in_range
from src.utils.time_utils import today as get_today

router = APIRouter(prefix="/agenda", tags=["agenda"])


@router.get("")
async def get_agenda(
    range: Optional[str] = "today",
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    all_tasks = task_service.task_store.load_all()

    if from_date and to_date:
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
    elif range == "today":
        start = end = get_today()
    elif range and range.endswith("d"):
        days = int(range[:-1])
        start = get_today()
        end = start + timedelta(days=days)
    else:
        start = end = get_today()

    tasks_in_range = get_tasks_in_range(all_tasks, start, end)
    sorted_tasks = sort_tasks_for_agenda(tasks_in_range)

    # 统计摘要
    summary = {
        "total": len(sorted_tasks),
        "pending": sum(1 for t in sorted_tasks if t.status == "pending"),
        "in_progress": sum(1 for t in sorted_tasks if t.status == "in_progress"),
        "overdue": sum(1 for t in sorted_tasks if t.is_overdue),
        "time_critical": sum(1 for t in sorted_tasks if t.timing_mode == "time_critical"),
    }

    # 未来7天重要事项（仅当查看 today 时附带）
    upcoming_important = []
    if range == "today":
        future_start = get_today() + timedelta(days=1)
        future_end = get_today() + timedelta(days=7)
        future_tasks = get_tasks_in_range(all_tasks, future_start, future_end)
        upcoming_important = [
            {
                "id": t.id,
                "title": t.title,
                "deadline": t.deadline.isoformat() if t.deadline else None,
                "days_until": (t.deadline.date() - get_today()).days if t.deadline else None,
            }
            for t in future_tasks
            if t.importance >= 3 or t.urgency >= 3
        ]

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "summary": summary,
        "tasks": [t.model_dump(mode="json") for t in sorted_tasks],
        "upcoming_important": upcoming_important,
    }
