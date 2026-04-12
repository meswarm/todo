"""APScheduler 调度引擎"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import (
    MORNING_PUSH_HOUR, MORNING_PUSH_MINUTE,
    EVENING_PUSH_HOUR, EVENING_PUSH_MINUTE,
)
from src.scheduler.overdue_scan import scan_overdue
from src.scheduler.reminder_scan import scan_reminders, has_imminent_critical_tasks
from src.scheduler.morning_push import morning_push
from src.scheduler.evening_push import evening_push
from src.scheduler.recurrence_gen import generate_recurring_tasks
from src.scheduler.stats_gen import generate_weekly_stats, generate_monthly_stats

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def _adaptive_reminder_scan():
    """自适应扫描：有卡点任务时30秒扫一次"""
    scan_reminders()
    if has_imminent_critical_tasks():
        if not scheduler.get_job("critical_fast_scan"):
            scheduler.add_job(
                scan_reminders,
                IntervalTrigger(seconds=30),
                id="critical_fast_scan",
                replace_existing=True,
            )
            logger.info("Activated fast scan for critical tasks")
    else:
        job = scheduler.get_job("critical_fast_scan")
        if job:
            scheduler.remove_job("critical_fast_scan")
            logger.info("Deactivated fast scan")


def start_scheduler():
    """启动所有定时任务"""
    # 重复任务生成 - 每日 00:30
    scheduler.add_job(
        generate_recurring_tasks,
        CronTrigger(hour=0, minute=30),
        id="recurrence_gen",
    )

    # 早晨推送
    scheduler.add_job(
        morning_push,
        CronTrigger(hour=MORNING_PUSH_HOUR, minute=MORNING_PUSH_MINUTE),
        id="morning_push",
    )

    # 晚间推送
    scheduler.add_job(
        evening_push,
        CronTrigger(hour=EVENING_PUSH_HOUR, minute=EVENING_PUSH_MINUTE),
        id="evening_push",
    )

    # 提醒扫描 - 每60秒
    scheduler.add_job(
        _adaptive_reminder_scan,
        IntervalTrigger(seconds=60),
        id="reminder_scan",
    )

    # 逾期扫描 - 每小时
    scheduler.add_job(
        scan_overdue,
        IntervalTrigger(hours=1),
        id="overdue_scan",
    )

    # 周统计 - 每周日 23:00
    scheduler.add_job(
        generate_weekly_stats,
        CronTrigger(day_of_week="sun", hour=23, minute=0),
        id="weekly_stats",
    )

    # 月统计 - 每月最后一天 23:00
    scheduler.add_job(
        generate_monthly_stats,
        CronTrigger(day="last", hour=23, minute=0),
        id="monthly_stats",
    )

    scheduler.start()
    logger.info("Scheduler started with all jobs")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
