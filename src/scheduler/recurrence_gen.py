"""Recurring-rule generation and 02:00 business-day rollover."""
from __future__ import annotations

import logging
from datetime import date, datetime, time

from src.config import RECURRENCES_FILE
from src.models import Recurrence, RecurrenceCreate, RecurrencePattern, Task, TaskCreate
from src.services import task_service
from src.services.business_day import BUSINESS_DAY_START_HOUR, business_date, business_day_range
from src.storage import JsonStore
from src.utils.id_gen import generate_recurrence_id

logger = logging.getLogger(__name__)
recurrence_store = JsonStore(RECURRENCES_FILE, Recurrence)


def should_generate(rec: Recurrence, day: date) -> bool:
    if not rec.enabled:
        return False
    if day < rec.start_date:
        return False
    if rec.end_date and day > rec.end_date:
        return False
    if rec.last_generated_for and rec.last_generated_for >= day:
        return False

    if rec.pattern == RecurrencePattern.DAILY:
        return True
    if rec.pattern == RecurrencePattern.WEEKLY:
        return day.isoweekday() in (rec.week_days or [])
    if rec.pattern == RecurrencePattern.MONTHLY:
        return day.day == rec.month_day
    if rec.pattern == RecurrencePattern.INTERVAL:
        if not rec.last_generated_for:
            return True
        return (day - rec.last_generated_for).days >= (rec.interval_days or 1)
    return False


def create_recurrence(payload: RecurrenceCreate) -> Recurrence:
    recurrence = Recurrence(id=generate_recurrence_id(), **payload.model_dump())
    recurrence_store.add(recurrence)
    return recurrence


def list_recurrences(enabled_only: bool = False) -> list[Recurrence]:
    recurrences = recurrence_store.load_all()
    if enabled_only:
        return [item for item in recurrences if item.enabled]
    return recurrences


def _scheduled_for(day: date, time_of_day: str) -> datetime:
    hour, minute = map(int, time_of_day.split(":"))
    return datetime.combine(day, time(hour=hour, minute=minute))


def generate_recurring_tasks(day: date | None = None) -> list[Task]:
    target_day = day or business_date()
    generated: list[Task] = []
    existing = task_service.task_store.load_all()
    existing_pairs = {
        (task.recurrence_id, business_date(task.scheduled_at))
        for task in existing
        if task.recurrence_id
    }

    for rec in recurrence_store.load_all():
        if not should_generate(rec, target_day):
            continue
        pair = (rec.id, target_day)
        if pair in existing_pairs:
            continue
        scheduled_at = _scheduled_for(target_day, rec.time_of_day)
        template = rec.template
        task = task_service.create_task(
            TaskCreate(
                title=template.title,
                scheduled_at=scheduled_at,
                detail=template.detail,
                recurrence_id=rec.id,
            )
        )
        generated.append(task)
        rec.last_generated_for = target_day
        recurrence_store.update(rec.id, rec)
        logger.info("Generated recurring task %s from %s", task.id, rec.id)
    return generated


def prepare_business_day(now: datetime | None = None) -> dict[str, int]:
    current = now or datetime.now()
    current_day = business_date(current)
    day_start, _ = business_day_range(current_day)
    archived = task_service.archive_before(day_start)
    generated = generate_recurring_tasks(current_day)
    logger.info(
        "Business day prepared for %s: archived=%s generated=%s",
        current_day.isoformat(),
        archived,
        len(generated),
    )
    return {"archived": archived, "generated": len(generated)}
