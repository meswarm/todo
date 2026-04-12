"""测试任务 CRUD API"""
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.storage import JsonStore
from src.models import Task


@pytest.fixture(autouse=True)
def setup_data(tmp_path, monkeypatch):
    """每个测试用独立的数据目录"""
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


def test_create_task():
    resp = client.post("/tasks", json={"title": "测试任务", "category": "工作"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试任务"
    assert data["status"] == "pending"


def test_list_tasks():
    client.post("/tasks", json={"title": "任务1", "category": "工作"})
    client.post("/tasks", json={"title": "任务2", "category": "生活"})
    resp = client.get("/tasks")
    assert len(resp.json()) == 2


def test_get_task():
    resp = client.post("/tasks", json={"title": "查找我", "category": "工作"})
    task_id = resp.json()["id"]
    resp = client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "查找我"


def test_update_task():
    resp = client.post("/tasks", json={"title": "旧标题", "category": "工作"})
    task_id = resp.json()["id"]
    resp = client.put(f"/tasks/{task_id}", json={"title": "新标题"})
    assert resp.json()["title"] == "新标题"


def test_delete_task():
    resp = client.post("/tasks", json={"title": "删我", "category": "工作"})
    task_id = resp.json()["id"]
    resp = client.delete(f"/tasks/{task_id}")
    assert resp.status_code == 200


def test_status_transition():
    resp = client.post("/tasks", json={"title": "流转", "category": "工作"})
    task_id = resp.json()["id"]
    # pending → in_progress
    resp = client.patch(f"/tasks/{task_id}/status",
                        json={"status": "in_progress"})
    assert resp.json()["status"] == "in_progress"


def test_invalid_status_transition():
    resp = client.post("/tasks", json={"title": "错误", "category": "工作"})
    task_id = resp.json()["id"]
    # pending → completed (should fail, must go through in_progress)
    resp = client.patch(f"/tasks/{task_id}/status",
                        json={"status": "completed"})
    assert resp.status_code == 400


def test_filter_by_category():
    client.post("/tasks", json={"title": "工作1", "category": "工作"})
    client.post("/tasks", json={"title": "生活1", "category": "生活"})
    resp = client.get("/tasks?category=工作")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["category"] == "工作"


def test_complete_task_moves_to_history():
    resp = client.post("/tasks", json={"title": "完成我", "category": "工作"})
    task_id = resp.json()["id"]
    # pending → in_progress → completed
    client.patch(f"/tasks/{task_id}/status", json={"status": "in_progress"})
    resp = client.patch(f"/tasks/{task_id}/status",
                        json={"status": "completed", "summary": "做完了"})
    assert resp.status_code == 200
    # 应该从活跃列表消失
    resp = client.get("/tasks")
    assert all(t["id"] != task_id for t in resp.json())
