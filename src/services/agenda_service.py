"""日程排序逻辑：依赖拓扑 + 优先级"""
from datetime import datetime, date

from src.models import Task, TaskStatus


def compute_priority_score(task: Task) -> float:
    """综合优先级得分（越高越优先）"""
    return task.urgency * task.importance


def topological_sort(tasks: list[Task]) -> list[Task]:
    """按依赖关系拓扑排序（被依赖的排前面）"""
    task_map = {t.id: t for t in tasks}
    in_degree = {t.id: 0 for t in tasks}
    adj: dict[str, list[str]] = {t.id: [] for t in tasks}

    for t in tasks:
        for dep_id in t.depends_on:
            if dep_id in task_map:
                adj[dep_id].append(t.id)
                in_degree[t.id] += 1

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    sorted_ids = []
    while queue:
        # 在同一层级中按优先级排序
        queue.sort(
            key=lambda tid: compute_priority_score(task_map[tid]),
            reverse=True,
        )
        tid = queue.pop(0)
        sorted_ids.append(tid)
        for next_id in adj[tid]:
            in_degree[next_id] -= 1
            if in_degree[next_id] == 0:
                queue.append(next_id)

    # 把没在拓扑排序中的也加上（有循环依赖的极端情况）
    for t in tasks:
        if t.id not in sorted_ids:
            sorted_ids.append(t.id)

    return [task_map[tid] for tid in sorted_ids]


def sort_tasks_for_agenda(tasks: list[Task]) -> list[Task]:
    """完整的日程排序：拓扑排序 → 逾期优先 → 卡点优先 → 综合得分 → 截止时间"""
    sorted_tasks = topological_sort(tasks)

    def sort_key(t: Task):
        overdue_priority = 0 if t.is_overdue else 1
        critical_priority = 0 if t.timing_mode == "time_critical" else 1
        score = -(t.urgency * t.importance)
        deadline_ts = t.deadline.timestamp() if t.deadline else float("inf")
        return (overdue_priority, critical_priority, score, deadline_ts)

    sorted_tasks.sort(key=sort_key)
    return sorted_tasks


def get_tasks_in_range(
    tasks: list[Task], start: date, end: date
) -> list[Task]:
    """获取指定日期范围内的任务（基于 deadline 或 scheduled_at）"""
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())
    result = []
    for t in tasks:
        if t.status in (TaskStatus.COMPLETED, TaskStatus.ABANDONED):
            continue
        in_range = False
        if t.deadline and start_dt <= t.deadline <= end_dt:
            in_range = True
        elif t.scheduled_at and start_dt <= t.scheduled_at <= end_dt:
            in_range = True
        elif not t.deadline and not t.scheduled_at:
            # 无日期的活跃任务只在 "today" 范围显示
            if start == end:
                in_range = True
        if in_range:
            result.append(t)
    return result
