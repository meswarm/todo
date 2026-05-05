"""Business-day helpers for a 02:00 day boundary."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

BUSINESS_DAY_START_HOUR = 2


def business_date(now: datetime | None = None) -> date:
    current = now or datetime.now()
    if current.hour < BUSINESS_DAY_START_HOUR:
        return current.date() - timedelta(days=1)
    return current.date()


def business_day_range(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(hour=BUSINESS_DAY_START_HOUR))
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start, end
