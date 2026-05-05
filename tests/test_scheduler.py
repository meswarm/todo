"""Tests for recurrence generation and reminder scanning."""
from __future__ import annotations

import json
from datetime import date, datetime

import src.scheduler.reminder_scan as reminder_scan
from src.models import Recurrence, RecurrencePattern, RecurrenceTemplate, Task
from src.scheduler.recurrence_gen import should_generate


def test_should_generate_daily():
    rec = Recurrence(
        id="rec_001",
        title="每日",
        pattern=RecurrencePattern.DAILY,
        template=RecurrenceTemplate(title="运动"),
        start_date=date(2026, 4, 1),
        last_generated_for=date(2026, 4, 11),
    )
    assert should_generate(rec, date(2026, 4, 12))
    assert not should_generate(rec, date(2026, 4, 11))


def test_should_generate_interval():
    rec = Recurrence(
        id="rec_002",
        title="隔天",
        pattern=RecurrencePattern.INTERVAL,
        template=RecurrenceTemplate(title="跑步"),
        interval_days=3,
        start_date=date(2026, 4, 1),
        last_generated_for=date(2026, 4, 9),
    )
    assert not should_generate(rec, date(2026, 4, 11))
    assert should_generate(rec, date(2026, 4, 12))


def test_should_generate_weekly():
    rec = Recurrence(
        id="rec_003",
        title="周一三五",
        pattern=RecurrencePattern.WEEKLY,
        template=RecurrenceTemplate(title="健身"),
        week_days=[1, 3, 5],
        start_date=date(2026, 4, 1),
    )
    assert should_generate(rec, date(2026, 4, 13))
    assert not should_generate(rec, date(2026, 4, 14))


def test_should_generate_monthly():
    rec = Recurrence(
        id="rec_004",
        title="每月15号",
        pattern=RecurrencePattern.MONTHLY,
        template=RecurrenceTemplate(title="交房租"),
        month_day=15,
        start_date=date(2026, 4, 1),
    )
    assert should_generate(rec, date(2026, 4, 15))
    assert not should_generate(rec, date(2026, 4, 14))


def test_reminder_still_fires_if_first_scan_happens_after_trigger_time(monkeypatch, tmp_path):
    task = Task(
        id="task_001",
        title="吃鱼油",
        scheduled_at=datetime(2026, 4, 20, 21, 59, 54),
        created_at=datetime(2026, 4, 20, 21, 54, 55),
    )

    pushed_payloads: list[dict] = []
    state_file = tmp_path / "reminder_state.json"
    state_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reminder_scan, "REMINDER_STATE_FILE", state_file)
    monkeypatch.setattr(reminder_scan.task_service.task_store, "load_all", lambda: [task])
    monkeypatch.setattr(
        reminder_scan,
        "publish_notification",
        lambda payload: pushed_payloads.append(payload) or True,
    )

    count = reminder_scan.scan_reminders(now=datetime(2026, 4, 20, 21, 55, 55))

    assert count == 1
    assert len(pushed_payloads) == 1
    assert pushed_payloads[0]["type"] == "task_reminder"
    assert pushed_payloads[0]["data"]["task"]["title"] == "吃鱼油"
    assert pushed_payloads[0]["data"]["task"]["detail"] == ""
    assert pushed_payloads[0]["data"]["task"]["completion_summary"] == ""
    assert json.loads(state_file.read_text(encoding="utf-8"))


def test_reminder_does_not_fire_before_trigger_time(monkeypatch, tmp_path):
    task = Task(
        id="task_002",
        title="吃鱼油",
        scheduled_at=datetime(2026, 4, 20, 21, 59, 54),
    )

    pushed_payloads: list[dict] = []
    state_file = tmp_path / "reminder_state.json"
    state_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reminder_scan, "REMINDER_STATE_FILE", state_file)
    monkeypatch.setattr(reminder_scan.task_service.task_store, "load_all", lambda: [task])
    monkeypatch.setattr(
        reminder_scan,
        "publish_notification",
        lambda payload: pushed_payloads.append(payload) or True,
    )

    count = reminder_scan.scan_reminders(now=datetime(2026, 4, 20, 21, 49, 30))

    assert count == 0
    assert pushed_payloads == []


def test_reminder_minutes_are_filtered_by_remaining_time(monkeypatch):
    task = Task(
        id="task_003",
        title="六分钟后开会",
        scheduled_at=datetime(2026, 4, 20, 20, 0, 0),
    )

    monkeypatch.setattr(reminder_scan, "TASK_REMINDER_MINUTES", [10, 5, 2])
    minutes = reminder_scan._effective_reminder_minutes(
        task,
        now=datetime(2026, 4, 20, 19, 54, 0),
    )

    assert minutes == [5, 2]


def test_reminder_minutes_can_become_empty_without_immediate_fallback(monkeypatch):
    task = Task(
        id="task_004",
        title="一分钟后开会",
        scheduled_at=datetime(2026, 4, 20, 20, 0, 0),
    )

    monkeypatch.setattr(reminder_scan, "TASK_REMINDER_MINUTES", [10, 5, 2])
    monkeypatch.setattr(reminder_scan, "REMINDER_MIN_LEAD_SECONDS", 30)
    minutes = reminder_scan._effective_reminder_minutes(
        task,
        now=datetime(2026, 4, 20, 19, 59, 31),
    )

    assert minutes == []
