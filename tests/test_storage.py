"""Tests for JSON storage."""
from datetime import datetime

import pytest

from src.models.task import Task
from src.storage.json_store import JsonStore


@pytest.fixture
def tmp_store(tmp_path):
    f = tmp_path / "test.json"
    f.write_text("[]")
    return JsonStore(f, Task)


@pytest.fixture
def sample_task():
    return Task(
        id="task_test_001",
        title="测试",
        scheduled_at=datetime(2026, 4, 28, 10, 30),
    )


def test_add_and_load(tmp_store, sample_task):
    tmp_store.add(sample_task)
    items = tmp_store.load_all()
    assert len(items) == 1
    assert items[0].title == "测试"


def test_find_by_id(tmp_store, sample_task):
    tmp_store.add(sample_task)
    found = tmp_store.find_by_id("task_test_001")
    assert found is not None
    assert found.id == "task_test_001"


def test_update(tmp_store, sample_task):
    tmp_store.add(sample_task)
    sample_task.title = "已修改"
    assert tmp_store.update("task_test_001", sample_task)
    found = tmp_store.find_by_id("task_test_001")
    assert found.title == "已修改"


def test_delete(tmp_store, sample_task):
    tmp_store.add(sample_task)
    assert tmp_store.delete("task_test_001")
    assert tmp_store.find_by_id("task_test_001") is None


def test_move_to(tmp_path, sample_task):
    f1 = tmp_path / "source.json"
    f2 = tmp_path / "target.json"
    f1.write_text("[]")
    f2.write_text("[]")
    source = JsonStore(f1, Task)
    target = JsonStore(f2, Task)
    source.add(sample_task)
    assert source.move_to("task_test_001", target)
    assert source.find_by_id("task_test_001") is None
    assert target.find_by_id("task_test_001") is not None
