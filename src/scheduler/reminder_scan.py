"""Scheduled reminder scanning with persisted dedupe state."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta

from src.config import (
    REMINDER_MIN_LEAD_SECONDS,
    REMINDER_STATE_FILE,
    SLOT_REMINDER_TIMES,
    TASK_REMINDER_MINUTES,
)
from src.models import Task, TimeKind, TimeSlot
from src.services import task_service
from src.services.agenda_service import sort_tasks_for_agenda
from src.services.business_day import business_date
from src.services.notification import publish_notification

logger = logging.getLogger(__name__)

AUTO_REMINDER_TRIGGER_WINDOW_SECONDS = 90
_SCAN_LOCK = threading.Lock()


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
    if task.time_kind == TimeKind.SLOT:
        return []
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
        "recurrence_id": task.recurrence_id,
        "time_kind": task.time_kind.value,
        "time_slot": task.time_slot.value if task.time_slot else None,
        "minutes_before": minutes_before,
    }


def _task_payload_without_minutes(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "title": task.title,
        "scheduled_at": task.scheduled_at.isoformat(),
        "detail": task.detail,
        "recurrence_id": task.recurrence_id,
        "time_kind": task.time_kind.value,
        "time_slot": task.time_slot.value if task.time_slot else None,
    }


def _slot_trigger_time(current: datetime, slot: str) -> datetime:
    return datetime.combine(business_date(current), SLOT_REMINDER_TIMES[slot])


def _slot_state_key(day: str, slot: str) -> str:
    return f"slot:{day}:{slot}:{SLOT_REMINDER_TIMES[slot].strftime('%H:%M')}"


def _scan_slot_reminders(tasks: list[Task], current: datetime, state: dict[str, str]) -> int:
    triggered = 0
    current_day = business_date(current)
    current_day_label = current_day.isoformat()

    for slot in [item.value for item in TimeSlot]:
        trigger_time = _slot_trigger_time(current, slot)
        delay_seconds = (current - trigger_time).total_seconds()
        if not 0 <= delay_seconds <= AUTO_REMINDER_TRIGGER_WINDOW_SECONDS:
            continue
        key = _slot_state_key(current_day_label, slot)
        if key in state:
            continue
        slot_tasks = sort_tasks_for_agenda(
            [
                task
                for task in tasks
                if not task.completed
                and task.time_kind == TimeKind.SLOT
                and task.time_slot == TimeSlot(slot)
                and business_date(task.scheduled_at) == current_day
            ]
        )
        if not slot_tasks:
            continue
        publish_notification(
            {
                "type": "slot_task_reminder",
                "timestamp": current.isoformat(),
                "data": {
                    "business_day": current_day_label,
                    "time_slot": slot,
                    "tasks": [_task_payload_without_minutes(task) for task in slot_tasks],
                    "reminder_reason": "slot_task_reminder",
                },
            }
        )
        state[key] = current.isoformat()
        triggered += 1
        logger.info("Slot reminder triggered for %s (%s tasks)", slot, len(slot_tasks))
    return triggered


def scan_reminders(now: datetime | None = None) -> int:
    with _SCAN_LOCK:
        current = now or datetime.now()
        state = _load_state()
        triggered = 0
        tasks = task_service.task_store.load_all()

        for task in tasks:
            if task.completed:
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

        triggered += _scan_slot_reminders(tasks, current, state)

        if triggered:
            _save_state(state)
        return triggered


def has_imminent_tasks(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    threshold = current + timedelta(minutes=15)
    for task in task_service.task_store.load_all():
        if task.completed:
            continue
        if task.time_kind == TimeKind.SLOT:
            continue
        if current <= task.scheduled_at <= threshold:
            return True
    return False
