"""每日早晨推送"""
import logging
from datetime import datetime, date, timedelta

from src.services import task_service
from src.services.agenda_service import sort_tasks_for_agenda, get_tasks_in_range
from src.services.webhook import push_webhook_sync

logger = logging.getLogger(__name__)


def morning_push():
    """推送今日日程 + 未来7天重要事项"""
    now = datetime.now()
    today = date.today()
    all_tasks = task_service.task_store.load_all()

    # 今日任务
    today_tasks = get_tasks_in_range(all_tasks, today, today)
    sorted_today = sort_tasks_for_agenda(today_tasks)

    # 未来7天重要任务
    future_start = today + timedelta(days=1)
    future_end = today + timedelta(days=7)
    future_tasks = get_tasks_in_range(all_tasks, future_start, future_end)
    upcoming = [
        {
            "id": t.id,
            "title": t.title,
            "deadline": t.deadline.isoformat() if t.deadline else None,
            "days_until": (t.deadline.date() - today).days if t.deadline else None,
            "urgency": t.urgency,
            "importance": t.importance,
        }
        for t in future_tasks
        if t.importance >= 2 or t.urgency >= 2
    ]

    overdue = [t for t in all_tasks if t.is_overdue]

    payload = {
        "type": "morning_agenda",
        "timestamp": now.isoformat(),
        "data": {
            "today_tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                    "urgency": t.urgency,
                    "importance": t.importance,
                    "difficulty": t.difficulty,
                    "estimated_minutes": t.estimated_minutes,
                    "timing_mode": t.timing_mode,
                    "depends_on": t.depends_on,
                    "subtasks_progress": (
                        f"{sum(1 for s in t.subtasks if s.status == 'completed')}/{len(t.subtasks)}"
                        if t.subtasks else None
                    ),
                }
                for t in sorted_today
            ],
            "overdue_tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                }
                for t in overdue
            ],
            "upcoming_important": upcoming,
            "stats_summary": {
                "today_total": len(sorted_today),
                "today_pending": sum(1 for t in sorted_today if t.status == "pending"),
                "today_in_progress": sum(1 for t in sorted_today if t.status == "in_progress"),
                "overdue_count": len(overdue),
                "time_critical_count": sum(
                    1 for t in sorted_today if t.timing_mode == "time_critical"
                ),
            },
        },
    }
    push_webhook_sync(payload)
    logger.info("Morning push completed")
