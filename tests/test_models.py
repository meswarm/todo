"""Tests for simplified task models."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.task import TaskCreate
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
    assert task.completion_summary == ""
    assert task.recurrence_id is None


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
