"""测试数据模型"""
import pytest
from src.models.task import Task, TaskCreate, TaskStatus, TimingMode
from src.utils.id_gen import generate_task_id, generate_sub_id


def test_task_create_minimal():
    tc = TaskCreate(title="测试任务", category="工作")
    assert tc.title == "测试任务"
    assert tc.urgency == 2  # 默认值
    assert tc.timing_mode == TimingMode.FLEXIBLE


def test_task_create_full():
    tc = TaskCreate(
        title="抢票", category="生活",
        urgency=3, importance=3, difficulty=1,
        timing_mode=TimingMode.TIME_CRITICAL,
    )
    assert tc.timing_mode == TimingMode.TIME_CRITICAL


def test_task_id_generation():
    id1 = generate_task_id()
    id2 = generate_task_id()
    assert id1 != id2
    assert id1.startswith("task_")


def test_sub_id_generation():
    sid = generate_sub_id(["sub_001", "sub_002"])
    assert sid == "sub_003"


def test_urgency_validation():
    with pytest.raises(Exception):
        TaskCreate(title="bad", category="x", urgency=5)
