"""统计数据模型"""
from pydantic import BaseModel, Field


class CategoryStat(BaseModel):
    category: str
    count: int
    percentage: float


class PeriodStats(BaseModel):
    """周期统计数据"""
    period: str                                          # "2026-W15" or "2026-04"
    total_tasks: int = 0
    completed: int = 0
    abandoned: int = 0
    overdue_completed: int = 0                           # 逾期后才完成的
    completion_rate: float = 0.0
    abandon_rate: float = 0.0
    procrastination_rate: float = 0.0
    avg_estimated_minutes: float = 0.0
    avg_actual_minutes: float = 0.0
    category_distribution: list[CategoryStat] = Field(default_factory=list)
    difficulty_distribution: dict[int, int] = Field(default_factory=dict)


class DailyStats(BaseModel):
    """当日统计"""
    date: str
    total: int = 0
    pending: int = 0
    in_progress: int = 0
    completed_today: int = 0
    abandoned_today: int = 0
    new_added: int = 0
    overdue: int = 0
    completion_rate: float = 0.0
