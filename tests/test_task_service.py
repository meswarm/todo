from datetime import datetime

from src.models import TaskComplete, TaskCreate
from src.services.business_day import business_date, business_day_range
from src.services import task_service
from src.storage import JsonStore
from src.models.task import Task


def test_business_date_before_2am_belongs_to_previous_day():
    assert business_date(datetime(2026, 4, 28, 1, 30)).isoformat() == "2026-04-27"


def test_business_date_after_2am_belongs_to_current_day():
    assert business_date(datetime(2026, 4, 28, 2, 0)).isoformat() == "2026-04-28"


def test_business_day_range_starts_at_2am():
    start, end = business_day_range(datetime(2026, 4, 28, 12, 0).date())
    assert start.isoformat() == "2026-04-28T02:00:00"
    assert end.isoformat() == "2026-04-29T01:59:59.999999"


def test_complete_task_keeps_task_active_until_archive(tmp_path, monkeypatch):
    tasks_file = tmp_path / "tasks.json"
    history_file = tmp_path / "history.json"
    tasks_file.write_text("[]", encoding="utf-8")
    history_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(task_service, "task_store", JsonStore(tasks_file, Task))
    monkeypatch.setattr(task_service, "history_store", JsonStore(history_file, Task))

    task = task_service.create_task(
        TaskCreate(
            title="开会",
            scheduled_at=datetime(2026, 4, 27, 21, 0),
            detail="今晚 9 点开会",
        )
    )

    completed = task_service.complete_task(
        task.id,
        TaskComplete(completion_summary="会议已完成"),
    )

    assert completed is not None
    assert completed.completed_at is not None
    assert task_service.task_store.find_by_id(task.id) is not None
    assert task_service.history_store.find_by_id(task.id) is None


def test_archive_before_moves_past_tasks_only(tmp_path, monkeypatch):
    tasks_file = tmp_path / "tasks.json"
    history_file = tmp_path / "history.json"
    tasks_file.write_text("[]", encoding="utf-8")
    history_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(task_service, "task_store", JsonStore(tasks_file, Task))
    monkeypatch.setattr(task_service, "history_store", JsonStore(history_file, Task))

    old_task = task_service.create_task(
        TaskCreate(
            title="旧任务",
            scheduled_at=datetime(2026, 4, 27, 21, 0),
        )
    )
    future_task = task_service.create_task(
        TaskCreate(
            title="未来任务",
            scheduled_at=datetime(2026, 4, 28, 21, 0),
        )
    )

    moved = task_service.archive_before(datetime(2026, 4, 28, 2, 0))

    assert moved == 1
    assert task_service.task_store.find_by_id(old_task.id) is None
    assert task_service.history_store.find_by_id(old_task.id) is not None
    assert task_service.task_store.find_by_id(future_task.id) is not None
