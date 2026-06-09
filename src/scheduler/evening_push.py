"""Evening report payloads for the next business day."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.services import task_service
from src.services.agenda_service import get_tasks_on_day, sort_tasks_for_agenda
from src.services.business_day import business_date
from src.services.notification import publish_notification

logger = logging.getLogger(__name__)


def evening_push(now: datetime | None = None) -> None:
    current = now or datetime.now()
    tomorrow = business_date(current) + timedelta(days=1)
    tomorrow_tasks = sort_tasks_for_agenda(
        get_tasks_on_day(task_service.task_store.load_all(), tomorrow),
    )

    publish_notification(
        {
            "type": "evening_agenda",
            "timestamp": current.isoformat(),
            "data": {
                "business_day": tomorrow.isoformat(),
                "tomorrow_tasks": [task.model_dump(mode="json") for task in tomorrow_tasks],
            },
        }
    )
    logger.info("Evening report completed")
