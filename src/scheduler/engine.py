"""APScheduler runtime for the simplified todo workflow."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import (
    EVENING_PUSH_HOUR,
    EVENING_PUSH_MINUTE,
    MORNING_PUSH_HOUR,
    MORNING_PUSH_MINUTE,
)
from src.scheduler.evening_push import evening_push
from src.scheduler.morning_push import morning_push
from src.scheduler.recurrence_gen import prepare_business_day
from src.scheduler.reminder_scan import has_imminent_tasks, scan_reminders

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def _adaptive_reminder_scan() -> None:
    scan_reminders()
    if has_imminent_tasks():
        if not scheduler.get_job("fast_reminder_scan"):
            scheduler.add_job(
                scan_reminders,
                IntervalTrigger(seconds=30),
                id="fast_reminder_scan",
                replace_existing=True,
            )
            logger.info("Activated fast reminder scan")
    else:
        job = scheduler.get_job("fast_reminder_scan")
        if job:
            scheduler.remove_job("critical_fast_scan")
            logger.info("Deactivated fast reminder scan")


def start_scheduler() -> None:
    if scheduler.running:
        return

    prepare_business_day()

    scheduler.add_job(
        prepare_business_day,
        CronTrigger(hour=2, minute=0),
        id="business_day_rollover",
        replace_existing=True,
    )
    scheduler.add_job(
        morning_push,
        CronTrigger(hour=MORNING_PUSH_HOUR, minute=MORNING_PUSH_MINUTE),
        id="morning_push",
        replace_existing=True,
    )
    scheduler.add_job(
        evening_push,
        CronTrigger(hour=EVENING_PUSH_HOUR, minute=EVENING_PUSH_MINUTE),
        id="evening_push",
        replace_existing=True,
    )
    scheduler.add_job(
        _adaptive_reminder_scan,
        IntervalTrigger(seconds=60),
        id="reminder_scan",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with simplified jobs")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
