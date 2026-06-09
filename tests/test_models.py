"""Tests for simplified task models."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.task import Task, TaskCreate, TimeKind, TimeSlot
from src.utils.id_gen import generate_sub_id, generate_task_id


def test_task_create_uses_minimal_task_fields():
    task = TaskCreate(
        title="写总结",
        scheduled_at=datetime(2026, 4, 28, 10, 30),
        detail="整理重构记录",
    )

    dumped = task.model_dump()
    assert "status" not in dumped
    assert "difficulty" not in dumped
    assert "time_mode" not in dumped
    assert "completion_summary" not in dumped
    assert "completed_at" not in dumped
    assert task.recurrence_id is None
    assert task.time_kind == TimeKind.EXACT
    assert task.time_slot is None


def test_legacy_task_defaults_to_exact_time():
    task = Task(
        id="26053101",
        title="写总结",
        scheduled_at=datetime(2026, 5, 31, 10, 30),
    )

    assert task.time_kind == TimeKind.EXACT
    assert task.time_slot is None


def test_slot_task_requires_time_slot():
    with pytest.raises(ValidationError):
        TaskCreate(
            title="买菜",
            scheduled_at=datetime(2026, 5, 31, 14, 0),
            time_kind=TimeKind.SLOT,
        )


def test_exact_task_clears_time_slot():
    task = TaskCreate(
        title="开会",
        scheduled_at=datetime(2026, 5, 31, 17, 0),
        time_kind=TimeKind.EXACT,
        time_slot=TimeSlot.AFTERNOON,
    )

    assert task.time_kind == TimeKind.EXACT
    assert task.time_slot is None


def test_slot_task_accepts_valid_time_slot():
    task = TaskCreate(
        title="买菜",
        scheduled_at=datetime(2026, 5, 31, 14, 0),
        time_kind=TimeKind.SLOT,
        time_slot=TimeSlot.AFTERNOON,
    )

    assert task.time_kind == TimeKind.SLOT
    assert task.time_slot == TimeSlot.AFTERNOON


def test_task_title_is_short():
    with pytest.raises(ValidationError):
        TaskCreate(
            title="这是一个明显超过十个字的任务标题",
            scheduled_at=datetime(2026, 4, 28, 10, 30),
            detail="x",
        )


def test_legacy_status_and_priority_fields_are_ignored():
    task = TaskCreate(
        title="散步",
        scheduled_at=datetime(2026, 4, 28, 10, 30),
        status="incomplete",
        difficulty=3,
        time_mode="time_critical",
    )

    dumped = task.model_dump()
    assert "status" not in dumped
    assert "difficulty" not in dumped
    assert "time_mode" not in dumped


def test_task_id_generation():
    id1 = generate_task_id()
    id2 = generate_task_id()
    assert id1 != id2
    assert len(id1) == 8
    assert id1.isdigit()


def test_task_id_generation_uses_existing_short_ids():
    prefix = datetime.now().strftime("%y%m%d")
    task_id = generate_task_id([f"{prefix}01", f"{prefix}02"])

    assert task_id.startswith(prefix)
    assert int(task_id[6:]) >= 3


def test_sub_id_generation():
    sid = generate_sub_id(["sub_001", "sub_002"])
    assert sid == "sub_003"
