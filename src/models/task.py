"""任务数据模型"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TimingMode(str, Enum):
    FLEXIBLE = "flexible"
    TIME_CRITICAL = "time_critical"


class ReminderType(str, Enum):
    BEFORE_DEADLINE = "before_deadline"
    FIXED_TIME = "fixed_time"


class Reminder(BaseModel):
    type: ReminderType
    minutes: Optional[int] = None        # for before_deadline
    time: Optional[datetime] = None      # for fixed_time
    triggered: bool = False


class SubTask(BaseModel):
    id: str
    title: str
    status: TaskStatus = TaskStatus.PENDING


class Note(BaseModel):
    time: datetime
    content: str


class Completion(BaseModel):
    completed_at: Optional[datetime] = None
    actual_minutes: Optional[int] = None
    summary: Optional[str] = None


class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    category: str
    tags: list[str] = Field(default_factory=list)

    urgency: int = Field(default=2, ge=1, le=3)
    importance: int = Field(default=2, ge=1, le=3)
    difficulty: int = Field(default=2, ge=1, le=3)
    estimated_minutes: Optional[int] = None

    timing_mode: TimingMode = TimingMode.FLEXIBLE

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deadline: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None

    reminders: list[Reminder] = Field(default_factory=list)
    recurrence_id: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)
    detail_doc: Optional[str] = None

    subtasks: list[SubTask] = Field(default_factory=list)
    notes: list[Note] = Field(default_factory=list)
    completion: Completion = Field(default_factory=Completion)
    is_overdue: bool = False


class TaskCreate(BaseModel):
    """创建任务的请求模型"""
    title: str
    description: Optional[str] = None
    category: str
    tags: list[str] = Field(default_factory=list)
    urgency: int = Field(default=2, ge=1, le=3)
    importance: int = Field(default=2, ge=1, le=3)
    difficulty: int = Field(default=2, ge=1, le=3)
    estimated_minutes: Optional[int] = None
    timing_mode: TimingMode = TimingMode.FLEXIBLE
    deadline: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    reminders: list[Reminder] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    subtasks: list[SubTask] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    """更新任务的请求模型（所有字段可选）"""
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    urgency: Optional[int] = Field(default=None, ge=1, le=3)
    importance: Optional[int] = Field(default=None, ge=1, le=3)
    difficulty: Optional[int] = Field(default=None, ge=1, le=3)
    estimated_minutes: Optional[int] = None
    timing_mode: Optional[TimingMode] = None
    deadline: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None


class StatusChange(BaseModel):
    """状态变更请求"""
    status: TaskStatus
    actual_minutes: Optional[int] = None
    summary: Optional[str] = None
