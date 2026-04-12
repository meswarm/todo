"""测试子任务、备注、详情文档 API"""
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.storage import JsonStore
from src.models import Task


@pytest.fixture(autouse=True)
def setup_data(tmp_path, monkeypatch):
    import src.config as cfg
    import src.services.task_service as ts

    tasks_file = tmp_path / "tasks.json"
    history_file = tmp_path / "history.json"
    docs_dir = tmp_path / "docs"
    tasks_file.write_text("[]")
    history_file.write_text("[]")
    docs_dir.mkdir()

    monkeypatch.setattr(cfg, "TASKS_FILE", tasks_file)
    monkeypatch.setattr(cfg, "HISTORY_FILE", history_file)
    monkeypatch.setattr(cfg, "DOCS_DIR", docs_dir)
    ts.task_store = JsonStore(tasks_file, Task)
    ts.history_store = JsonStore(history_file, Task)


client = TestClient(app)


@pytest.fixture
def task_id():
    resp = client.post("/tasks", json={"title": "父任务", "category": "工作"})
    return resp.json()["id"]


def test_add_subtask(task_id):
    resp = client.post(f"/tasks/{task_id}/subtasks", json={"title": "子任务1"})
    assert resp.status_code == 201
    assert resp.json()["id"] == "sub_001"


def test_update_subtask(task_id):
    client.post(f"/tasks/{task_id}/subtasks", json={"title": "子任务1"})
    resp = client.patch(f"/tasks/{task_id}/subtasks/sub_001",
                        json={"status": "completed"})
    assert resp.json()["status"] == "completed"


def test_delete_subtask(task_id):
    client.post(f"/tasks/{task_id}/subtasks", json={"title": "子任务1"})
    resp = client.delete(f"/tasks/{task_id}/subtasks/sub_001")
    assert resp.status_code == 200


def test_add_note(task_id):
    resp = client.post(f"/tasks/{task_id}/notes", json={"content": "备注内容"})
    assert resp.status_code == 201
    assert resp.json()["content"] == "备注内容"


def test_get_notes(task_id):
    client.post(f"/tasks/{task_id}/notes", json={"content": "备注1"})
    client.post(f"/tasks/{task_id}/notes", json={"content": "备注2"})
    resp = client.get(f"/tasks/{task_id}/notes")
    assert len(resp.json()) == 2


def test_detail_doc(task_id):
    content = "# 详情\n\n详细步骤..."
    resp = client.put(f"/tasks/{task_id}/detail", json={"content": content})
    assert resp.status_code == 200
    resp = client.get(f"/tasks/{task_id}/detail")
    assert resp.text == content


def test_set_dependencies(task_id):
    resp = client.put(f"/tasks/{task_id}/dependencies",
                      json=["task_other_001"])
    assert resp.json()["depends_on"] == ["task_other_001"]


def test_set_reminders(task_id):
    reminders = [{"type": "before_deadline", "minutes": 30}]
    resp = client.put(f"/tasks/{task_id}/reminders", json=reminders)
    assert resp.status_code == 200
    assert len(resp.json()["reminders"]) == 1
