"""Scheduled reminder scanning with persisted dedupe state."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from src.config import (
    REMINDER_MIN_LEAD_SECONDS,
    REMINDER_STATE_FILE,
    TASK_REMINDER_MINUTES,
)
from src.models import Task
from src.services import task_service
from src.services.notification import publish_notification

logger = logging.getLogger(__name__)

AUTO_REMINDER_TRIGGER_WINDOW_SECONDS = 90


def _load_state() -> dict[str, str]:
    if not REMINDER_STATE_FILE.exists():
        return {}
    text = REMINDER_STATE_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def _save_state(state: dict[str, str]) -> None:
    REMINDER_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _effective_reminder_minutes(task: Task, now: datetime) -> list[int]:
    remaining = task.scheduled_at - now
    remaining_seconds = remaining.total_seconds()
    minutes: list[int] = []
    for item in TASK_REMINDER_MINUTES:
        lead_seconds = item * 60
        if (
            lead_seconds >= REMINDER_MIN_LEAD_SECONDS
            and lead_seconds <= remaining_seconds + AUTO_REMINDER_TRIGGER_WINDOW_SECONDS
        ):
            minutes.append(item)
    return minutes


def _task_payload(task: Task, minutes_before: int) -> dict[str, object]:
    return {
        "id": task.id,
        "title": task.title,
        "scheduled_at": task.scheduled_at.isoformat(),
        "detail": task.detail,
        "completion_summary": task.completion_summary,
        "recurrence_id": task.recurrence_id,
        "minutes_before": minutes_before,
    }


def scan_reminders(now: datetime | None = None) -> int:
    current = now or datetime.now()
    state = _load_state()
    triggered = 0

    for task in task_service.task_store.load_all():
        if task.completed_at is not None:
            continue
        for minutes_before in _effective_reminder_minutes(task, current):
            trigger_time = task.scheduled_at - timedelta(minutes=minutes_before)
            delay_seconds = (current - trigger_time).total_seconds()
            key = f"{task.id}:{minutes_before}:{task.scheduled_at.isoformat()}"
            if key in state:
                continue
            if 0 <= delay_seconds <= AUTO_REMINDER_TRIGGER_WINDOW_SECONDS:
                publish_notification(
                    {
                        "type": "task_reminder",
                        "timestamp": current.isoformat(),
                        "data": {
                            "task": _task_payload(task, minutes_before),
                            "reminder_reason": "task_reminder",
                        },
                    }
                )
                state[key] = current.isoformat()
                triggered += 1
                logger.info("Reminder triggered for %s (%s min)", task.id, minutes_before)

    if triggered:
        _save_state(state)
    return triggered


def has_imminent_tasks(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    threshold = current + timedelta(minutes=15)
    for task in task_service.task_store.load_all():
        if (
            task.completed_at is None
            and current <= task.scheduled_at <= threshold
        ):
            return True
    return False
