"""Task data models for the simplified todo runtime."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class TimeKind(str, Enum):
    EXACT = "exact"
    SLOT = "slot"


class TimeSlot(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class Task(BaseModel):
    id: str
    title: str = Field(max_length=10)
    scheduled_at: datetime
    created_at: datetime = Field(default_factory=datetime.now)
    detail: str = ""
    recurrence_id: Optional[str] = None
    time_kind: TimeKind = TimeKind.EXACT
    time_slot: Optional[TimeSlot] = None
    completed: bool = False

    @model_validator(mode="after")
    def validate_time_semantics(self) -> "Task":
        if self.time_kind == TimeKind.SLOT and self.time_slot is None:
            raise ValueError("slot tasks require time_slot")
        if self.time_kind == TimeKind.EXACT:
            self.time_slot = None
        return self


class TaskCreate(BaseModel):
    title: str = Field(max_length=10)
    scheduled_at: datetime
    detail: str = ""
    recurrence_id: Optional[str] = None
    time_kind: TimeKind = TimeKind.EXACT
    time_slot: Optional[TimeSlot] = None
    completed: bool = False

    @model_validator(mode="after")
    def validate_time_semantics(self) -> "TaskCreate":
        if self.time_kind == TimeKind.SLOT and self.time_slot is None:
            raise ValueError("slot tasks require time_slot")
        if self.time_kind == TimeKind.EXACT:
            self.time_slot = None
        return self


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=10)
    scheduled_at: Optional[datetime] = None
    detail: Optional[str] = None
    recurrence_id: Optional[str] = None
    time_kind: Optional[TimeKind] = None
    time_slot: Optional[TimeSlot] = None
    completed: Optional[bool] = None

    @model_validator(mode="after")
    def validate_time_semantics(self) -> "TaskUpdate":
        if self.time_kind == TimeKind.SLOT and self.time_slot is None:
            raise ValueError("slot updates require time_slot")
        if self.time_kind == TimeKind.EXACT:
            self.time_slot = None
        return self
