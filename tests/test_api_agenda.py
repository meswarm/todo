"""测试日程视图和搜索 API"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from src.main import app
from src.storage import JsonStore
from src.models import Task


@pytest.fixture(autouse=True)
def setup_data(tmp_path, monkeypatch):
    import src.config as cfg
    import src.services.task_service as ts

    tasks_file = tmp_path / "tasks.json"
    history_file = tmp_path / "history.json"
    tasks_file.write_text("[]")
    history_file.write_text("[]")

    monkeypatch.setattr(cfg, "TASKS_FILE", tasks_file)
    monkeypatch.setattr(cfg, "HISTORY_FILE", history_file)
    ts.task_store = JsonStore(tasks_file, Task)
    ts.history_store = JsonStore(history_file, Task)


client = TestClient(app)


def test_agenda_today():
    tomorrow = (datetime.now() + timedelta(hours=2)).isoformat()
    client.post("/tasks", json={
        "title": "今天的任务", "category": "工作",
        "deadline": tomorrow,
    })
    resp = client.get("/agenda?range=today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total"] >= 1


def test_agenda_7d():
    future = (datetime.now() + timedelta(days=3)).isoformat()
    client.post("/tasks", json={
        "title": "三天后的任务", "category": "工作",
        "deadline": future,
    })
    resp = client.get("/agenda?range=7d")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total"] >= 1


def test_agenda_custom_range():
    future = (datetime.now() + timedelta(days=5)).isoformat()
    client.post("/tasks", json={
        "title": "五天后的任务", "category": "工作",
        "deadline": future,
    })
    from_date = datetime.now().strftime("%Y-%m-%d")
    to_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    resp = client.get(f"/agenda?from={from_date}&to={to_date}")
    assert resp.status_code == 200


def test_search_by_keyword():
    client.post("/tasks", json={"title": "学习Python", "category": "学习"})
    client.post("/tasks", json={"title": "买菜", "category": "生活"})
    resp = client.get("/tasks/search?q=Python")
    data = resp.json()
    assert data["count"] == 1
    assert "Python" in data["results"][0]["title"]


def test_search_in_tags():
    client.post("/tasks", json={
        "title": "运动",
        "category": "健康",
        "tags": ["跑步", "马拉松"],
    })
    resp = client.get("/tasks/search?q=马拉松")
    assert resp.json()["count"] == 1


def test_search_empty():
    resp = client.get("/tasks/search?q=不存在的关键词")
    assert resp.json()["count"] == 0


def test_search_scope_active():
    client.post("/tasks", json={"title": "活跃任务", "category": "工作"})
    resp = client.get("/tasks/search?q=活跃&scope=active")
    assert resp.json()["count"] == 1
