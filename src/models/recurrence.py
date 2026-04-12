"""重复规则数据模型"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RecurrencePattern(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    INTERVAL = "interval"


class TaskTemplate(BaseModel):
    """从重复规则生成任务时使用的模板"""
    title: str
    description: Optional[str] = None
    category: str
    tags: list[str] = Field(default_factory=list)
    urgency: int = Field(default=2, ge=1, le=3)
    importance: int = Field(default=2, ge=1, le=3)
    difficulty: int = Field(default=2, ge=1, le=3)
    estimated_minutes: Optional[int] = None
    timing_mode: str = "flexible"


class Recurrence(BaseModel):
    id: str
    title: str
    task_template: TaskTemplate
    pattern: RecurrencePattern
    interval_days: Optional[int] = None       # for interval pattern
    week_days: Optional[list[int]] = None     # for weekly: [1,3,5] = Mon,Wed,Fri
    month_day: Optional[int] = None           # for monthly: 1-31
    time_of_day: str = "09:00"                # HH:MM
    start_date: date
    end_date: Optional[date] = None
    enabled: bool = True
    last_generated: Optional[date] = None


class RecurrenceCreate(BaseModel):
    title: str
    task_template: TaskTemplate
    pattern: RecurrencePattern
    interval_days: Optional[int] = None
    week_days: Optional[list[int]] = None
    month_day: Optional[int] = None
    time_of_day: str = "09:00"
    start_date: date
    end_date: Optional[date] = None
