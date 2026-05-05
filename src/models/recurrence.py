"""Recurring task rule models."""
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
    start_date: date
    end_date: Optional[date] = None
    enabled: bool = True
    last_generated_for: Optional[date] = None


class RecurrenceCreate(BaseModel):
    title: str
    template: RecurrenceTemplate
    pattern: RecurrencePattern
    interval_days: Optional[int] = None
    week_days: Optional[list[int]] = None
    month_day: Optional[int] = None
    time_of_day: str = "09:00"
    start_date: date
    end_date: Optional[date] = None
    enabled: bool = True
