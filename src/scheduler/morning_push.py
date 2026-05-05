"""Morning push payloads for the current business day."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.services import task_service
from src.services.agenda_service import get_tasks_in_range, sort_tasks_for_agenda
from src.services.business_day import business_date
from src.services.notification import publish_notification

logger = logging.getLogger(__name__)


def morning_push(now: datetime | None = None) -> None:
    current = now or datetime.now()
    today = business_date(current)
    all_tasks = task_service.task_store.load_all()
    today_tasks = sort_tasks_for_agenda(get_tasks_in_range(all_tasks, today, today))
    future_tasks = sort_tasks_for_agenda(
        [
            task
            for task in all_tasks
            if business_date(task.scheduled_at) > today and task.recurrence_id is None
        ]
    )

    publish_notification(
        {
            "type": "morning_agenda",
            "timestamp": current.isoformat(),
            "data": {
                "business_day": today.isoformat(),
                "today_tasks": [task.model_dump(mode="json") for task in today_tasks],
                "future_tasks": [task.model_dump(mode="json") for task in future_tasks],
            },
        }
    )
    logger.info("Morning push completed")

