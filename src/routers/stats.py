"""统计 API"""
import json
from datetime import date

from fastapi import APIRouter, HTTPException

import src.config as config
from src.scheduler.stats_gen import compute_daily_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/daily")
async def get_daily_stats(date_str: str | None = None):
    target = date.fromisoformat(date_str) if date_str else date.today()
    return compute_daily_stats(target)


@router.get("/weekly")
async def get_weekly_stats(week: str):
    path = config.STATS_DIR / "weekly" / f"{week}.json"
    if not path.exists():
        raise HTTPException(404, f"No stats for week {week}")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/monthly")
async def get_monthly_stats(month: str):
    path = config.STATS_DIR / "monthly" / f"{month}.json"
    if not path.exists():
        raise HTTPException(404, f"No stats for month {month}")
    return json.loads(path.read_text(encoding="utf-8"))
