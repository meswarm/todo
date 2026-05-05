"""Evening review payloads for the current business day."""
from __future__ import annotations

import logging
from datetime import datetime

from src.services import task_service
from src.services.agenda_service import get_tasks_in_range, sort_tasks_for_agenda
from src.services.business_day import business_date
from src.services.notification import publish_notification

logger = logging.getLogger(__name__)


def evening_push(now: datetime | None = None) -> None:
    current = now or datetime.now()
    today = business_date(current)
    today_tasks = sort_tasks_for_agenda(
        get_tasks_in_range(task_service.task_store.load_all(), today, today),
    )
    completed = [task for task in today_tasks if task.completed_at is not None]
    incomplete = [task for task in today_tasks if task.completed_at is None]

    publish_notification(
        {
            "type": "evening_review",
            "timestamp": current.isoformat(),
            "data": {
                "business_day": today.isoformat(),
                "completed_tasks": [task.model_dump(mode="json") for task in completed],
                "incomplete_tasks": [task.model_dump(mode="json") for task in incomplete],
            },
        }
    )
    logger.info("Evening push completed")
