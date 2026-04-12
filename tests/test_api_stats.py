"""测试统计和重复任务 API"""
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.storage import JsonStore
from src.models import Task, Recurrence


@pytest.fixture(autouse=True)
def setup_data(tmp_path, monkeypatch):
    import src.config as cfg
    import src.services.task_service as ts
    import src.routers.recurrences as rec_router
    import src.scheduler.recurrence_gen as rec_gen

    for name in ["tasks", "history", "recurrences"]:
        f = tmp_path / f"{name}.json"
        f.write_text("[]")

    stats_dir = tmp_path / "stats"
    (stats_dir / "weekly").mkdir(parents=True)
    (stats_dir / "monthly").mkdir(parents=True)

    monkeypatch.setattr(cfg, "TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(cfg, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(cfg, "RECURRENCES_FILE", tmp_path / "recurrences.json")
    monkeypatch.setattr(cfg, "STATS_DIR", stats_dir)

    ts.task_store = JsonStore(tmp_path / "tasks.json", Task)
    ts.history_store = JsonStore(tmp_path / "history.json", Task)
    rec_router.recurrence_store = JsonStore(tmp_path / "recurrences.json", Recurrence)
    rec_gen.recurrence_store = JsonStore(tmp_path / "recurrences.json", Recurrence)


client = TestClient(app)


def test_daily_stats():
    client.post("/tasks", json={"title": "任务1", "category": "工作"})
    resp = client.get("/stats/daily")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data


def test_create_recurrence():
    resp = client.post("/recurrences", json={
        "title": "每日运动",
        "task_template": {"title": "运动30分钟", "category": "健康"},
        "pattern": "daily",
        "start_date": "2026-04-12",
    })
    assert resp.status_code == 201
    assert resp.json()["pattern"] == "daily"


def test_list_recurrences():
    client.post("/recurrences", json={
        "title": "每日运动",
        "task_template": {"title": "运动", "category": "健康"},
        "pattern": "daily",
        "start_date": "2026-04-12",
    })
    resp = client.get("/recurrences")
    assert len(resp.json()) == 1


def test_delete_recurrence():
    resp = client.post("/recurrences", json={
        "title": "删除测试",
        "task_template": {"title": "x", "category": "x"},
        "pattern": "daily",
        "start_date": "2026-04-12",
    })
    rec_id = resp.json()["id"]
    resp = client.delete(f"/recurrences/{rec_id}")
    assert resp.status_code == 200


def test_create_interval_recurrence():
    resp = client.post("/recurrences", json={
        "title": "隔两天跑步",
        "task_template": {"title": "跑步5公里", "category": "健康"},
        "pattern": "interval",
        "interval_days": 2,
        "start_date": "2026-04-12",
    })
    assert resp.status_code == 201
    assert resp.json()["interval_days"] == 2
