"""时间工具"""
from __future__ import annotations

from datetime import datetime, date, timedelta


def now() -> datetime:
    return datetime.now()


def today() -> date:
    return date.today()


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def parse_datetime(s: str) -> datetime:
    return datetime.fromisoformat(s)


def date_range(range_str: str) -> tuple[date, date]:
    """解析范围字符串: today, 7d, 30d → (start, end)"""
    start = today()
    if range_str == "today":
        return start, start
    elif range_str.endswith("d"):
        days = int(range_str[:-1])
        return start, start + timedelta(days=days)
    raise ValueError(f"Unknown range: {range_str}")


def get_week_number(d: date | None = None) -> str:
    """返回 ISO 周号字符串: 2026-W15"""
    d = d or today()
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def get_month_str(d: date | None = None) -> str:
    """返回月份字符串: 2026-04"""
    d = d or today()
    return d.strftime("%Y-%m")
