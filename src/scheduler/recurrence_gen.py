"""重复任务生成"""
import logging
from datetime import date, datetime

from src.config import RECURRENCES_FILE
from src.storage import JsonStore
from src.models import Recurrence, Task
from src.services import task_service
from src.utils.id_gen import generate_task_id

logger = logging.getLogger(__name__)
recurrence_store = JsonStore(RECURRENCES_FILE, Recurrence)


def should_generate(rec: Recurrence, today: date) -> bool:
    """判断今天是否需要生成任务"""
    if not rec.enabled:
        return False
    if rec.end_date and today > rec.end_date:
        return False
    if today < rec.start_date:
        return False
    if rec.last_generated and rec.last_generated >= today:
        return False

    if rec.pattern == "daily":
        return True
    elif rec.pattern == "weekly":
        # isoweekday: 1=Mon, 7=Sun
        return today.isoweekday() in (rec.week_days or [])
    elif rec.pattern == "monthly":
        return today.day == rec.month_day
    elif rec.pattern == "interval":
        if not rec.last_generated:
            return True
        days_since = (today - rec.last_generated).days
        return days_since >= (rec.interval_days or 1)
    return False


def generate_recurring_tasks():
    """生成今日的重复任务实例"""
    today = date.today()
    recs = recurrence_store.load_all()

    for rec in recs:
        if should_generate(rec, today):
            tmpl = rec.task_template
            # 解析时间
            hour, minute = map(int, rec.time_of_day.split(":"))
            deadline = datetime.combine(today, datetime.min.time()).replace(
                hour=hour, minute=minute
            )

            task = Task(
                id=generate_task_id(),
                title=tmpl.title,
                description=tmpl.description,
                category=tmpl.category,
                tags=tmpl.tags,
                urgency=tmpl.urgency,
                importance=tmpl.importance,
                difficulty=tmpl.difficulty,
                estimated_minutes=tmpl.estimated_minutes,
                timing_mode=tmpl.timing_mode,
                deadline=deadline,
                recurrence_id=rec.id,
            )
            task_service.task_store.add(task)
            rec.last_generated = today
            recurrence_store.update(rec.id, rec)
            logger.info(f"Generated recurring task: {task.title} from {rec.id}")
