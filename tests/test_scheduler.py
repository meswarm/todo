"""测试调度器核心逻辑"""
from datetime import date

from src.scheduler.recurrence_gen import should_generate
from src.models import Recurrence, TaskTemplate, RecurrencePattern


def test_should_generate_daily():
    rec = Recurrence(
        id="rec_001", title="每日", pattern=RecurrencePattern.DAILY,
        task_template=TaskTemplate(title="运动", category="健康"),
        start_date=date(2026, 4, 1),
        last_generated=date(2026, 4, 11),
    )
    assert should_generate(rec, date(2026, 4, 12))
    assert not should_generate(rec, date(2026, 4, 11))  # 已生成


def test_should_generate_interval():
    rec = Recurrence(
        id="rec_002", title="隔天", pattern=RecurrencePattern.INTERVAL,
        task_template=TaskTemplate(title="跑步", category="健康"),
        interval_days=3,
        start_date=date(2026, 4, 1),
        last_generated=date(2026, 4, 9),
    )
    assert not should_generate(rec, date(2026, 4, 11))   # 差2天
    assert should_generate(rec, date(2026, 4, 12))        # 差3天


def test_should_generate_weekly():
    rec = Recurrence(
        id="rec_003", title="周一三五", pattern=RecurrencePattern.WEEKLY,
        task_template=TaskTemplate(title="健身", category="健康"),
        week_days=[1, 3, 5],
        start_date=date(2026, 4, 1),
    )
    # 2026-04-13 是周一
    assert should_generate(rec, date(2026, 4, 13))
    # 2026-04-14 是周二
    assert not should_generate(rec, date(2026, 4, 14))


def test_should_generate_monthly():
    rec = Recurrence(
        id="rec_004", title="每月15号", pattern=RecurrencePattern.MONTHLY,
        task_template=TaskTemplate(title="交房租", category="生活"),
        month_day=15,
        start_date=date(2026, 4, 1),
    )
    assert should_generate(rec, date(2026, 4, 15))
    assert not should_generate(rec, date(2026, 4, 14))


def test_should_not_generate_disabled():
    rec = Recurrence(
        id="rec_005", title="已禁用", pattern=RecurrencePattern.DAILY,
        task_template=TaskTemplate(title="x", category="x"),
        start_date=date(2026, 4, 1),
        enabled=False,
    )
    assert not should_generate(rec, date(2026, 4, 12))


def test_should_not_generate_past_end_date():
    rec = Recurrence(
        id="rec_006", title="已结束", pattern=RecurrencePattern.DAILY,
        task_template=TaskTemplate(title="x", category="x"),
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
    )
    assert not should_generate(rec, date(2026, 4, 12))
