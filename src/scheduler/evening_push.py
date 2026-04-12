"""每日晚间推送（复盘）"""
import logging
from datetime import datetime, date

from src.services import task_service
from src.services.webhook import push_webhook_sync

logger = logging.getLogger(__name__)


def evening_push():
    """推送当日复盘 + 逾期处理提醒"""
    now = datetime.now()
    today = date.today()

    # 今日完成的（在历史中查找 completed_at 是今天的）
    history = task_service.history_store.load_all()
    completed_today = [
        t for t in history
        if t.completion.completed_at
        and t.completion.completed_at.date() == today
        and t.status == "completed"
    ]
    abandoned_today = [
        t for t in history
        if t.completion.completed_at
        and t.completion.completed_at.date() == today
        and t.status == "abandoned"
    ]

    # 活跃但逾期的任务
    active = task_service.task_store.load_all()
    overdue = [t for t in active if t.is_overdue]

    # 今日未完成的（有 deadline 是今天但还没完成的）
    incomplete = [
        t for t in active
        if t.deadline and t.deadline.date() == today
        and t.status in ("pending", "in_progress")
    ]

    total = len(completed_today) + len(incomplete) + len(abandoned_today)

    payload = {
        "type": "evening_review",
        "timestamp": now.isoformat(),
        "data": {
            "completed_today": [
                {
                    "id": t.id,
                    "title": t.title,
                    "actual_minutes": t.completion.actual_minutes,
                    "summary": t.completion.summary,
                }
                for t in completed_today
            ],
            "incomplete_today": [
                {
                    "id": t.id,
                    "title": t.title,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                }
                for t in incomplete
            ],
            "overdue_tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                    "overdue_hours": round(
                        (now - t.deadline).total_seconds() / 3600, 1
                    ) if t.deadline else 0,
                    "options": ["continue_tomorrow", "abandon", "simplify"],
                }
                for t in overdue
            ],
            "daily_stats": {
                "completed": len(completed_today),
                "abandoned": len(abandoned_today),
                "new_added": sum(
                    1 for t in active if t.created_at.date() == today
                ),
                "completion_rate": round(
                    len(completed_today) / total, 2
                ) if total > 0 else 0,
            },
        },
    }
    push_webhook_sync(payload)
    logger.info("Evening push completed")
