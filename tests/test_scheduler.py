"""Tests for recurrence generation and reminder scanning."""
from __future__ import annotations

import json
import threading
import time as pytime
from datetime import date, datetime, time

import src.scheduler.reminder_scan as reminder_scan
from src.scheduler.morning_push import morning_push
from src.scheduler.noon_push import noon_push
from src.scheduler.evening_push import evening_push
from src.models import Recurrence, RecurrencePattern, RecurrenceTemplate, RecurrenceUpdate, Task, TimeKind, TimeSlot
from src.scheduler.recurrence_gen import should_generate, skip_recurrence_occurrence, update_recurrence
from src.storage import JsonStore


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


def test_should_not_generate_skipped_recurrence_day():
    rec = Recurrence(
        id="rec_skip",
        title="每日",
        pattern=RecurrencePattern.DAILY,
        template=RecurrenceTemplate(title="运动"),
        start_date=date(2026, 4, 1),
        skipped_dates=[date(2026, 6, 3)],
    )

    assert not should_generate(rec, date(2026, 6, 3))
    assert should_generate(rec, date(2026, 6, 4))


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


def test_update_recurrence_keeps_generated_tasks_and_last_generated_for(monkeypatch, tmp_path):
    recurrences_file = tmp_path / "recurrences.json"
    tasks_file = tmp_path / "tasks.json"
    recurrences_file.write_text("[]", encoding="utf-8")
    tasks_file.write_text("[]", encoding="utf-8")
    import src.scheduler.recurrence_gen as recurrence_gen

    monkeypatch.setattr(recurrence_gen, "recurrence_store", JsonStore(recurrences_file, Recurrence))
    monkeypatch.setattr(recurrence_gen.task_service, "task_store", JsonStore(tasks_file, Task))

    recurrence = Recurrence(
        id="rec_20260428_001",
        title="每日铲屎喂粮",
        pattern=RecurrencePattern.DAILY,
        time_of_day="08:00",
        start_date=date(2026, 4, 28),
        last_generated_for=date(2026, 5, 31),
        template=RecurrenceTemplate(title="每日铲屎喂粮", detail="每天清理猫砂。"),
    )
    generated_task = Task(
        id="26053101",
        title="每日铲屎喂粮",
        scheduled_at=datetime(2026, 5, 31, 8, 0),
        detail="每天清理猫砂。",
        recurrence_id=recurrence.id,
    )
    recurrence_gen.recurrence_store.add(recurrence)
    recurrence_gen.task_service.task_store.add(generated_task)

    updated = update_recurrence(
        recurrence.id,
        RecurrenceUpdate(time_of_day="09:30", template_title="喂猫", detail="上午处理"),
    )

    assert updated is not None
    assert updated.time_of_day == "09:30"
    assert updated.template.title == "喂猫"
    assert updated.template.detail == "上午处理"
    assert updated.last_generated_for == date(2026, 5, 31)
    stored_task = recurrence_gen.task_service.task_store.find_by_id("26053101")
    assert stored_task is not None
    assert stored_task.scheduled_at == datetime(2026, 5, 31, 8, 0)
    assert stored_task.title == "每日铲屎喂粮"


def test_skip_recurrence_occurrence_persists_skipped_day(monkeypatch, tmp_path):
    recurrences_file = tmp_path / "recurrences.json"
    recurrences_file.write_text("[]", encoding="utf-8")
    import src.scheduler.recurrence_gen as recurrence_gen

    monkeypatch.setattr(recurrence_gen, "recurrence_store", JsonStore(recurrences_file, Recurrence))
    recurrence_gen.recurrence_store.add(
        Recurrence(
            id="rec_20260428_001",
            title="每日铲屎喂粮",
            pattern=RecurrencePattern.DAILY,
            time_of_day="08:00",
            start_date=date(2026, 4, 28),
            template=RecurrenceTemplate(title="每日铲屎喂粮"),
        )
    )

    assert skip_recurrence_occurrence("rec_20260428_001", date(2026, 6, 3)) is True

    stored = recurrence_gen.recurrence_store.find_by_id("rec_20260428_001")
    assert stored is not None
    assert stored.skipped_dates == [date(2026, 6, 3)]


def test_generate_recurring_task_preserves_slot_semantics(monkeypatch, tmp_path):
    recurrences_file = tmp_path / "recurrences.json"
    tasks_file = tmp_path / "tasks.json"
    recurrences_file.write_text("[]", encoding="utf-8")
    tasks_file.write_text("[]", encoding="utf-8")
    import src.scheduler.recurrence_gen as recurrence_gen

    monkeypatch.setattr(recurrence_gen, "recurrence_store", JsonStore(recurrences_file, Recurrence))
    monkeypatch.setattr(recurrence_gen.task_service, "task_store", JsonStore(tasks_file, Task))

    recurrence_gen.recurrence_store.add(
        Recurrence(
            id="rec_20260428_001",
            title="每日铲屎喂粮",
            pattern=RecurrencePattern.DAILY,
            time_of_day="08:00",
            time_slot=TimeSlot.MORNING,
            start_date=date(2026, 6, 1),
            template=RecurrenceTemplate(title="每日铲屎喂粮"),
        )
    )

    generated = recurrence_gen.generate_recurring_tasks(date(2026, 6, 1))

    assert len(generated) == 1
    assert generated[0].time_kind == TimeKind.SLOT
    assert generated[0].time_slot == TimeSlot.MORNING


def test_morning_push_publishes_today_tasks_only(monkeypatch):
    today_task = Task(
        id="26053101",
        title="今日事",
        scheduled_at=datetime(2026, 5, 31, 9, 0),
    )
    tomorrow_task = Task(
        id="26060101",
        title="明日事",
        scheduled_at=datetime(2026, 6, 1, 9, 0),
    )
    pushed_payloads: list[dict] = []
    import src.scheduler.morning_push as morning_push_module

    monkeypatch.setattr(
        morning_push_module.task_service.task_store,
        "load_all",
        lambda: [today_task, tomorrow_task],
    )
    monkeypatch.setattr(
        morning_push_module,
        "publish_notification",
        lambda payload: pushed_payloads.append(payload),
    )

    morning_push(now=datetime(2026, 5, 31, 7, 0))

    assert pushed_payloads[0]["type"] == "morning_agenda"
    assert [task["id"] for task in pushed_payloads[0]["data"]["today_tasks"]] == [
        "26053101"
    ]
    assert "future_tasks" not in pushed_payloads[0]["data"]


def test_noon_push_publishes_today_tasks_only(monkeypatch):
    today_task = Task(
        id="26060201",
        title="中午事",
        scheduled_at=datetime(2026, 6, 2, 14, 0),
    )
    tomorrow_task = Task(
        id="26060301",
        title="明日事",
        scheduled_at=datetime(2026, 6, 3, 9, 0),
    )
    pushed_payloads: list[dict] = []
    import src.scheduler.noon_push as noon_push_module

    monkeypatch.setattr(
        noon_push_module.task_service.task_store,
        "load_all",
        lambda: [today_task, tomorrow_task],
    )
    monkeypatch.setattr(
        noon_push_module,
        "publish_notification",
        lambda payload: pushed_payloads.append(payload),
    )

    noon_push(now=datetime(2026, 6, 2, 12, 0))

    assert pushed_payloads[0]["type"] == "noon_agenda"
    assert pushed_payloads[0]["data"]["business_day"] == "2026-06-02"
    assert [task["id"] for task in pushed_payloads[0]["data"]["today_tasks"]] == [
        "26060201"
    ]
    assert "tomorrow_tasks" not in pushed_payloads[0]["data"]


def test_evening_push_publishes_tomorrow_tasks_only(monkeypatch):
    today_task = Task(
        id="26053101",
        title="今日事",
        scheduled_at=datetime(2026, 5, 31, 21, 0),
    )
    tomorrow_task = Task(
        id="26060101",
        title="明日事",
        scheduled_at=datetime(2026, 6, 1, 9, 0),
    )
    pushed_payloads: list[dict] = []
    import src.scheduler.evening_push as evening_push_module

    monkeypatch.setattr(
        evening_push_module.task_service.task_store,
        "load_all",
        lambda: [today_task, tomorrow_task],
    )
    monkeypatch.setattr(
        evening_push_module,
        "publish_notification",
        lambda payload: pushed_payloads.append(payload),
    )

    evening_push(now=datetime(2026, 5, 31, 23, 0))

    assert pushed_payloads[0]["type"] == "evening_agenda"
    assert pushed_payloads[0]["data"]["business_day"] == "2026-06-01"
    assert [task["id"] for task in pushed_payloads[0]["data"]["tomorrow_tasks"]] == [
        "26060101"
    ]
    assert "today_tasks" not in pushed_payloads[0]["data"]


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
    assert "completion_summary" not in pushed_payloads[0]["data"]["task"]
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


def test_completed_task_does_not_fire_reminder(monkeypatch, tmp_path):
    task = Task(
        id="task_done",
        title="买菜",
        scheduled_at=datetime(2026, 6, 3, 20, 0, 0),
        completed=True,
    )

    pushed_payloads: list[dict] = []
    state_file = tmp_path / "reminder_state.json"
    state_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reminder_scan, "REMINDER_STATE_FILE", state_file)
    monkeypatch.setattr(reminder_scan, "TASK_REMINDER_MINUTES", [5])
    monkeypatch.setattr(reminder_scan.task_service.task_store, "load_all", lambda: [task])
    monkeypatch.setattr(
        reminder_scan,
        "publish_notification",
        lambda payload: pushed_payloads.append(payload) or True,
    )

    count = reminder_scan.scan_reminders(now=datetime(2026, 6, 3, 19, 55, 10))

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


def test_slot_task_does_not_use_per_task_reminder_minutes(monkeypatch, tmp_path):
    task = Task(
        id="task_005",
        title="买菜",
        scheduled_at=datetime(2026, 5, 31, 14, 0, 0),
        time_kind=TimeKind.SLOT,
        time_slot=TimeSlot.AFTERNOON,
    )

    pushed_payloads: list[dict] = []
    state_file = tmp_path / "reminder_state.json"
    state_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reminder_scan, "REMINDER_STATE_FILE", state_file)
    monkeypatch.setattr(reminder_scan, "TASK_REMINDER_MINUTES", [25])
    monkeypatch.setattr(reminder_scan.task_service.task_store, "load_all", lambda: [task])
    monkeypatch.setattr(
        reminder_scan,
        "publish_notification",
        lambda payload: pushed_payloads.append(payload) or True,
    )

    count = reminder_scan.scan_reminders(now=datetime(2026, 5, 31, 13, 35, 0))

    assert count == 0
    assert pushed_payloads == []


def test_concurrent_reminder_scans_do_not_duplicate_exact_reminder(monkeypatch, tmp_path):
    task = Task(
        id="task_010",
        title="买榴莲",
        scheduled_at=datetime(2026, 5, 31, 20, 0, 0),
        time_kind=TimeKind.EXACT,
    )

    pushed_payloads: list[dict] = []
    state_file = tmp_path / "reminder_state.json"
    state_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reminder_scan, "REMINDER_STATE_FILE", state_file)
    monkeypatch.setattr(reminder_scan, "TASK_REMINDER_MINUTES", [5])
    monkeypatch.setattr(reminder_scan.task_service.task_store, "load_all", lambda: [task])

    def fake_publish(payload: dict) -> bool:
        pushed_payloads.append(payload)
        pytime.sleep(0.05)
        return True

    monkeypatch.setattr(reminder_scan, "publish_notification", fake_publish)

    results: list[int] = []

    def worker() -> None:
        results.append(reminder_scan.scan_reminders(now=datetime(2026, 5, 31, 19, 55, 10)))

    first = threading.Thread(target=worker)
    second = threading.Thread(target=worker)
    first.start()
    second.start()
    first.join()
    second.join()

    assert sum(results) == 1
    assert len(pushed_payloads) == 1
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert "task_010:5:2026-05-31T20:00:00" in state


def test_slot_reminder_groups_tasks_by_business_day_and_slot(monkeypatch, tmp_path):
    afternoon_one = Task(
        id="task_006",
        title="买菜",
        scheduled_at=datetime(2026, 5, 31, 14, 0, 0),
        time_kind=TimeKind.SLOT,
        time_slot=TimeSlot.AFTERNOON,
    )
    afternoon_two = Task(
        id="task_007",
        title="取快递",
        scheduled_at=datetime(2026, 5, 31, 14, 0, 0),
        time_kind=TimeKind.SLOT,
        time_slot=TimeSlot.AFTERNOON,
    )
    exact_task = Task(
        id="task_008",
        title="开会",
        scheduled_at=datetime(2026, 5, 31, 14, 0, 0),
        time_kind=TimeKind.EXACT,
    )

    pushed_payloads: list[dict] = []
    state_file = tmp_path / "reminder_state.json"
    state_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reminder_scan, "REMINDER_STATE_FILE", state_file)
    monkeypatch.setattr(
        reminder_scan,
        "SLOT_REMINDER_TIMES",
        {"morning": time(8, 0), "afternoon": time(14, 0), "evening": time(18, 0)},
    )
    monkeypatch.setattr(
        reminder_scan.task_service.task_store,
        "load_all",
        lambda: [afternoon_one, afternoon_two, exact_task],
    )
    monkeypatch.setattr(
        reminder_scan,
        "publish_notification",
        lambda payload: pushed_payloads.append(payload) or True,
    )

    count = reminder_scan.scan_reminders(now=datetime(2026, 5, 31, 14, 0, 30))

    assert count == 1
    assert pushed_payloads[0]["type"] == "slot_task_reminder"
    assert pushed_payloads[0]["data"]["business_day"] == "2026-05-31"
    assert pushed_payloads[0]["data"]["time_slot"] == "afternoon"
    assert [task["id"] for task in pushed_payloads[0]["data"]["tasks"]] == [
        "task_006",
        "task_007",
    ]
    assert "task_008" not in json.dumps(pushed_payloads[0], ensure_ascii=False)
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert "slot:2026-05-31:afternoon:14:00" in state


def test_slot_reminder_does_not_catch_up_after_window(monkeypatch, tmp_path):
    task = Task(
        id="task_009",
        title="买菜",
        scheduled_at=datetime(2026, 5, 31, 14, 0, 0),
        time_kind=TimeKind.SLOT,
        time_slot=TimeSlot.AFTERNOON,
    )

    pushed_payloads: list[dict] = []
    state_file = tmp_path / "reminder_state.json"
    state_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reminder_scan, "REMINDER_STATE_FILE", state_file)
    monkeypatch.setattr(
        reminder_scan,
        "SLOT_REMINDER_TIMES",
        {"morning": time(8, 0), "afternoon": time(14, 0), "evening": time(18, 0)},
    )
    monkeypatch.setattr(reminder_scan.task_service.task_store, "load_all", lambda: [task])
    monkeypatch.setattr(
        reminder_scan,
        "publish_notification",
        lambda payload: pushed_payloads.append(payload) or True,
    )

    count = reminder_scan.scan_reminders(now=datetime(2026, 5, 31, 14, 2, 0))

    assert count == 0
    assert pushed_payloads == []
