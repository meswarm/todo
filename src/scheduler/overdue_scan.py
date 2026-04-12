"""逾期任务扫描"""
import logging
from datetime import datetime

from src.services import task_service
from src.models import TaskStatus

logger = logging.getLogger(__name__)


def scan_overdue():
    """扫描并标记逾期任务"""
    now = datetime.now()
    tasks = task_service.task_store.load_all()
    for task in tasks:
        if (task.deadline
                and task.deadline < now
                and task.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
                and not task.is_overdue):
            task.is_overdue = True
            task.updated_at = now
            task_service.task_store.update(task.id, task)
            logger.info(f"Marked overdue: {task.id} - {task.title}")
