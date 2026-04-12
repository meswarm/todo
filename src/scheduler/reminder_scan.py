"""即时提醒扫描"""
import logging
from datetime import datetime, timedelta

from src.services import task_service
from src.services.webhook import push_webhook_sync
from src.models import TaskStatus, ReminderType, TimingMode

logger = logging.getLogger(__name__)

# 记录已触发的自动提醒，避免重复触发
_triggered_auto_reminders: set[str] = set()


def _get_auto_reminder_minutes(task) -> list[int]:
    """根据 timing_mode 返回自动提醒的提前分钟列表"""
    if not task.deadline:
        return []
    if task.timing_mode == TimingMode.TIME_CRITICAL:
        return [5, 2, 1]
    else:
        return [30]


def scan_reminders():
    """扫描需要触发的提醒"""
    now = datetime.now()
    tasks = task_service.task_store.load_all()

    for task in tasks:
        if task.status in (TaskStatus.COMPLETED, TaskStatus.ABANDONED):
            continue

        # 检查自定义提醒
        updated = False
        for i, reminder in enumerate(task.reminders):
            if reminder.triggered:
                continue
            trigger_time = None
            if reminder.type == ReminderType.BEFORE_DEADLINE:
                if task.deadline and reminder.minutes:
                    trigger_time = task.deadline - timedelta(minutes=reminder.minutes)
            elif reminder.type == ReminderType.FIXED_TIME:
                trigger_time = reminder.time

            if trigger_time and now >= trigger_time:
                push_webhook_sync({
                    "type": "task_reminder",
                    "timestamp": now.isoformat(),
                    "data": {
                        "task": {
                            "id": task.id,
                            "title": task.title,
                            "deadline": task.deadline.isoformat() if task.deadline else None,
                            "timing_mode": task.timing_mode,
                        },
                        "reminder_reason": "custom_reminder",
                    },
                })
                task.reminders[i].triggered = True
                updated = True
                logger.info(f"Reminder triggered: {task.id} - {task.title}")

        if updated:
            task_service.task_store.update(task.id, task)

        # 检查自动提醒（timing_mode 默认）
        if task.deadline:
            for minutes_before in _get_auto_reminder_minutes(task):
                trigger_time = task.deadline - timedelta(minutes=minutes_before)
                key = f"{task.id}:{minutes_before}"
                # 只在触发窗口内（前后1分钟）触发一次
                if (key not in _triggered_auto_reminders
                        and abs((now - trigger_time).total_seconds()) < 60):
                    push_webhook_sync({
                        "type": "task_reminder",
                        "timestamp": now.isoformat(),
                        "data": {
                            "task": {
                                "id": task.id,
                                "title": task.title,
                                "deadline": task.deadline.isoformat(),
                                "timing_mode": task.timing_mode,
                                "minutes_until": minutes_before,
                            },
                            "reminder_reason": f"auto_{task.timing_mode}_reminder",
                        },
                    })
                    _triggered_auto_reminders.add(key)
                    logger.info(
                        f"Auto reminder: {task.id} in {minutes_before}min"
                    )


def has_imminent_critical_tasks() -> bool:
    """检查是否有15分钟内即将触发的卡点任务"""
    now = datetime.now()
    threshold = now + timedelta(minutes=15)
    for task in task_service.task_store.load_all():
        if (task.timing_mode == TimingMode.TIME_CRITICAL
                and task.deadline
                and now <= task.deadline <= threshold
                and task.status not in (TaskStatus.COMPLETED, TaskStatus.ABANDONED)):
            return True
    return False
