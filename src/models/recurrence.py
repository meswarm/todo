"""Recurring task rule models."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from src.models.task import TimeSlot


class RecurrencePattern(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    INTERVAL = "interval"


class RecurrenceTemplate(BaseModel):
    title: str = Field(max_length=10)
    detail: str = ""


class Recurrence(BaseModel):
    id: str
    title: str
    template: RecurrenceTemplate
    pattern: RecurrencePattern
    interval_days: Optional[int] = None
    week_days: Optional[list[int]] = None
    month_day: Optional[int] = None
    time_of_day: str = "09:00"
    time_slot: Optional[TimeSlot] = None
    start_date: date
    end_date: Optional[date] = None
    enabled: bool = True
    last_generated_for: Optional[date] = None
    skipped_dates: list[date] = Field(default_factory=list)


class RecurrenceCreate(BaseModel):
    title: str
    template: RecurrenceTemplate
    pattern: RecurrencePattern
    interval_days: Optional[int] = None
    week_days: Optional[list[int]] = None
    month_day: Optional[int] = None
    time_of_day: str = "09:00"
    time_slot: Optional[TimeSlot] = None
    start_date: date
    end_date: Optional[date] = None
    enabled: bool = True


class RecurrenceUpdate(BaseModel):
    title: Optional[str] = None
    template_title: Optional[str] = Field(default=None, max_length=10)
    detail: Optional[str] = None
    pattern: Optional[RecurrencePattern] = None
    interval_days: Optional[int] = None
    week_days: Optional[list[int]] = None
    month_day: Optional[int] = None
    time_of_day: Optional[str] = None
    time_slot: Optional[TimeSlot] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    enabled: Optional[bool] = None
