"""Noon report payloads for the current business day."""
from __future__ import annotations

import logging
from datetime import datetime

from src.services import task_service
from src.services.agenda_service import get_tasks_on_day, sort_tasks_for_agenda
from src.services.business_day import business_date
from src.services.notification import publish_notification

logger = logging.getLogger(__name__)


def noon_push(now: datetime | None = None) -> None:
    current = now or datetime.now()
    today = business_date(current)
    today_tasks = sort_tasks_for_agenda(
        get_tasks_on_day(task_service.task_store.load_all(), today),
    )

    publish_notification(
        {
            "type": "noon_agenda",
            "timestamp": current.isoformat(),
            "data": {
                "business_day": today.isoformat(),
                "today_tasks": [task.model_dump(mode="json") for task in today_tasks],
            },
        }
    )
    logger.info("Noon report completed")
