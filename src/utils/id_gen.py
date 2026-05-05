"""ID 生成器"""
from datetime import datetime
import threading
import re

_counter_lock = threading.Lock()
_daily_counters: dict[str, int] = {}
_SHORT_TASK_ID_RE = re.compile(r"^(\d{6})(\d{2,})$")


def generate_task_id(existing_ids: list[str] | None = None) -> str:
    """生成格式为 YYMMDDNN 的短任务 ID，例如 26042701。"""
    today = datetime.now().strftime("%y%m%d")
    with _counter_lock:
        if existing_ids:
            _daily_counters[today] = max(
                _daily_counters.get(today, 0),
                _max_existing_task_number(today, existing_ids),
            )
        _daily_counters.setdefault(today, 0)
        _daily_counters[today] += 1
        return f"{today}{_daily_counters[today]:02d}"


def generate_sub_id(existing_ids: list[str]) -> str:
    """生成子任务 ID: sub_NNN"""
    max_n = 0
    for sid in existing_ids:
        if sid.startswith("sub_"):
            try:
                n = int(sid.split("_")[1])
                max_n = max(max_n, n)
            except (IndexError, ValueError):
                pass
    return f"sub_{max_n + 1:03d}"


def generate_recurrence_id() -> str:
    """生成重复规则 ID: rec_YYYYMMDD_NNN"""
    today = datetime.now().strftime("%Y%m%d")
    with _counter_lock:
        key = f"rec_{today}"
        _daily_counters.setdefault(key, 0)
        _daily_counters[key] += 1
        return f"rec_{today}_{_daily_counters[key]:03d}"


def init_counters_from_existing(task_ids: list[str]):
    """从已有任务 ID 初始化计数器（启动时调用，避免 ID 冲突）"""
    with _counter_lock:
        today = datetime.now().strftime("%y%m%d")
        _daily_counters[today] = max(
            _daily_counters.get(today, 0),
            _max_existing_task_number(today, task_ids),
        )
        for tid in task_ids:
            parts = tid.split("_")
            if len(parts) >= 3 and parts[0] == "task":
                date_str = parts[1]
                try:
                    num = int(parts[2])
                    _daily_counters[date_str] = max(
                        _daily_counters.get(date_str, 0), num
                    )
                except ValueError:
                    pass


def _max_existing_task_number(today: str, task_ids: list[str]) -> int:
    max_n = 0
    for tid in task_ids:
        match = _SHORT_TASK_ID_RE.match(tid)
        if match and match.group(1) == today:
            max_n = max(max_n, int(match.group(2)))
    return max_n
