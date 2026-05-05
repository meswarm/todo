"""Task data models for the simplified todo runtime."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Task(BaseModel):
    id: str
    title: str = Field(max_length=10)
    scheduled_at: datetime
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    detail: str = ""
    completion_summary: str = ""
    recurrence_id: Optional[str] = None


class TaskCreate(BaseModel):
    title: str = Field(max_length=10)
    scheduled_at: datetime
    detail: str = ""
    completion_summary: str = ""
    recurrence_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=10)
    scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    detail: Optional[str] = None
    completion_summary: Optional[str] = None
    recurrence_id: Optional[str] = None


class TaskComplete(BaseModel):
    completion_summary: str = ""
    completed_at: Optional[datetime] = None
