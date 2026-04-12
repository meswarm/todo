"""统计快照生成"""
import logging
from datetime import date
from collections import Counter

from src.config import STATS_DIR
from src.services import task_service
from src.models import PeriodStats, CategoryStat, DailyStats
from src.utils.time_utils import get_week_number, get_month_str

logger = logging.getLogger(__name__)


def _compute_stats(tasks: list, period: str) -> PeriodStats:
    """计算一组任务的统计数据"""
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == "completed")
    abandoned = sum(1 for t in tasks if t.status == "abandoned")
    overdue_completed = sum(
        1 for t in tasks
        if t.status == "completed" and t.is_overdue
    )
    cat_counter = Counter(t.category for t in tasks)
    cat_dist = [
        CategoryStat(
            category=cat, count=cnt,
            percentage=round(cnt / total * 100, 1) if total else 0,
        )
        for cat, cnt in cat_counter.most_common()
    ]
    diff_dist = Counter(t.difficulty for t in tasks)

    est_minutes = [t.estimated_minutes for t in tasks if t.estimated_minutes]
    act_minutes = [
        t.completion.actual_minutes for t in tasks
        if t.completion and t.completion.actual_minutes
    ]

    return PeriodStats(
        period=period,
        total_tasks=total,
        completed=completed,
        abandoned=abandoned,
        overdue_completed=overdue_completed,
        completion_rate=round(completed / total, 2) if total else 0,
        abandon_rate=round(abandoned / total, 2) if total else 0,
        procrastination_rate=round(overdue_completed / completed, 2) if completed else 0,
        avg_estimated_minutes=round(
            sum(est_minutes) / len(est_minutes), 1
        ) if est_minutes else 0,
        avg_actual_minutes=round(
            sum(act_minutes) / len(act_minutes), 1
        ) if act_minutes else 0,
        category_distribution=cat_dist,
        difficulty_distribution=dict(diff_dist),
    )


def generate_weekly_stats():
    """生成本周统计"""
    today = date.today()
    week_str = get_week_number(today)
    history = task_service.history_store.load_all()
    iso_year, iso_week, _ = today.isocalendar()
    week_tasks = [
        t for t in history
        if t.completion.completed_at
        and t.completion.completed_at.date().isocalendar()[:2] == (iso_year, iso_week)
    ]
    stats = _compute_stats(week_tasks, week_str)
    out_path = STATS_DIR / "weekly" / f"{week_str}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(stats.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Weekly stats generated: {week_str}")


def generate_monthly_stats():
    """生成本月统计"""
    today = date.today()
    month_str = get_month_str(today)
    history = task_service.history_store.load_all()
    month_tasks = [
        t for t in history
        if t.completion.completed_at
        and t.completion.completed_at.strftime("%Y-%m") == month_str
    ]
    stats = _compute_stats(month_tasks, month_str)
    out_path = STATS_DIR / "monthly" / f"{month_str}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(stats.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"Monthly stats generated: {month_str}")


def compute_daily_stats(target_date: date) -> DailyStats:
    """实时计算当日统计"""
    active = task_service.task_store.load_all()
    history = task_service.history_store.load_all()

    today_active = [
        t for t in active if t.deadline and t.deadline.date() == target_date
    ]
    today_completed = [
        t for t in history
        if t.completion.completed_at and t.completion.completed_at.date() == target_date
        and t.status == "completed"
    ]
    today_abandoned = [
        t for t in history
        if t.completion.completed_at and t.completion.completed_at.date() == target_date
        and t.status == "abandoned"
    ]
    new_added = [t for t in active if t.created_at.date() == target_date]

    total = len(today_active) + len(today_completed) + len(today_abandoned)
    return DailyStats(
        date=target_date.isoformat(),
        total=total,
        pending=sum(1 for t in today_active if t.status == "pending"),
        in_progress=sum(1 for t in today_active if t.status == "in_progress"),
        completed_today=len(today_completed),
        abandoned_today=len(today_abandoned),
        new_added=len(new_added),
        overdue=sum(1 for t in active if t.is_overdue),
        completion_rate=round(len(today_completed) / total, 2) if total else 0,
    )
