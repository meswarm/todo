"""端到端集成测试"""
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

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    stats_dir = tmp_path / "stats"
    (stats_dir / "weekly").mkdir(parents=True)
    (stats_dir / "monthly").mkdir(parents=True)

    monkeypatch.setattr(cfg, "TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(cfg, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(cfg, "RECURRENCES_FILE", tmp_path / "recurrences.json")
    monkeypatch.setattr(cfg, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(cfg, "STATS_DIR", stats_dir)

    ts.task_store = JsonStore(tmp_path / "tasks.json", Task)
    ts.history_store = JsonStore(tmp_path / "history.json", Task)
    rec_router.recurrence_store = JsonStore(tmp_path / "recurrences.json", Recurrence)
    rec_gen.recurrence_store = JsonStore(tmp_path / "recurrences.json", Recurrence)


client = TestClient(app)


def test_full_task_lifecycle():
    """完整任务生命周期: 创建 → 子任务 → 备注 → 详情 → 开始 → 完成"""
    # 1. 创建任务
    resp = client.post("/tasks", json={
        "title": "完成项目报告",
        "category": "工作",
        "urgency": 3,
        "importance": 3,
        "difficulty": 2,
        "estimated_minutes": 120,
        "tags": ["报告", "Q2"],
    })
    assert resp.status_code == 201
    task = resp.json()
    task_id = task["id"]
    assert task["status"] == "pending"

    # 2. 添加子任务
    for title in ["收集数据", "制作图表", "撰写分析"]:
        resp = client.post(f"/tasks/{task_id}/subtasks", json={"title": title})
        assert resp.status_code == 201

    # 3. 验证子任务
    resp = client.get(f"/tasks/{task_id}")
    assert len(resp.json()["subtasks"]) == 3

    # 4. 完成一个子任务
    resp = client.patch(f"/tasks/{task_id}/subtasks/sub_001",
                        json={"status": "completed"})
    assert resp.json()["status"] == "completed"

    # 5. 添加备注
    resp = client.post(f"/tasks/{task_id}/notes",
                       json={"content": "数据已从财务部获取"})
    assert resp.status_code == 201

    # 6. 添加详情文档
    detail_content = "# 项目报告\n\n## 数据来源\n- 财务部\n- 销售部\n\n## 参考链接\n- https://example.com/data"
    resp = client.put(f"/tasks/{task_id}/detail",
                      json={"content": detail_content})
    assert resp.status_code == 200

    # 7. 获取详情文档
    resp = client.get(f"/tasks/{task_id}/detail")
    assert "项目报告" in resp.text

    # 8. 开始执行
    resp = client.patch(f"/tasks/{task_id}/status",
                        json={"status": "in_progress"})
    assert resp.json()["status"] == "in_progress"

    # 9. 完成任务
    resp = client.patch(f"/tasks/{task_id}/status", json={
        "status": "completed",
        "actual_minutes": 100,
        "summary": "比预期提前完成，图表部分使用了新工具效率很高",
    })
    assert resp.json()["status"] == "completed"

    # 10. 确认已移到历史
    resp = client.get("/tasks")
    assert all(t["id"] != task_id for t in resp.json())

    # 11. 可以搜索到历史记录
    resp = client.get("/tasks/search?q=项目报告&scope=history")
    assert resp.json()["count"] == 1


def test_task_with_dependencies():
    """任务依赖关系测试"""
    # 创建两个任务
    resp1 = client.post("/tasks", json={"title": "准备材料", "category": "工作"})
    id1 = resp1.json()["id"]

    resp2 = client.post("/tasks", json={
        "title": "提交申请", "category": "工作",
        "depends_on": [id1],
    })
    id2 = resp2.json()["id"]

    # 验证依赖
    resp = client.get(f"/tasks/{id2}")
    assert id1 in resp.json()["depends_on"]

    # agenda 应该按依赖排序
    resp = client.get("/agenda?range=today")
    tasks = resp.json()["tasks"]
    task_ids = [t["id"] for t in tasks]
    if id1 in task_ids and id2 in task_ids:
        assert task_ids.index(id1) < task_ids.index(id2)


def test_recurrence_crud():
    """重复任务 CRUD 测试"""
    # 创建
    resp = client.post("/recurrences", json={
        "title": "每周一三五健身",
        "task_template": {
            "title": "去健身房",
            "category": "健康",
            "urgency": 2,
            "importance": 3,
            "estimated_minutes": 60,
        },
        "pattern": "weekly",
        "week_days": [1, 3, 5],
        "time_of_day": "18:00",
        "start_date": "2026-04-13",
    })
    assert resp.status_code == 201
    rec_id = resp.json()["id"]
    assert resp.json()["week_days"] == [1, 3, 5]

    # 列表
    resp = client.get("/recurrences")
    assert len(resp.json()) == 1

    # 删除
    resp = client.delete(f"/recurrences/{rec_id}")
    assert resp.status_code == 200
    resp = client.get("/recurrences")
    assert len(resp.json()) == 0


def test_reminder_and_timing_mode():
    """提醒和时间模式测试"""
    # 创建卡点任务
    resp = client.post("/tasks", json={
        "title": "抢演唱会门票",
        "category": "生活",
        "timing_mode": "time_critical",
        "urgency": 3,
        "importance": 3,
        "deadline": "2026-04-15T10:00:00",
    })
    task_id = resp.json()["id"]
    assert resp.json()["timing_mode"] == "time_critical"

    # 设置自定义提醒
    resp = client.put(f"/tasks/{task_id}/reminders", json=[
        {"type": "before_deadline", "minutes": 10},
        {"type": "before_deadline", "minutes": 5},
    ])
    assert len(resp.json()["reminders"]) == 2


def test_stats_api():
    """统计 API 测试"""
    client.post("/tasks", json={"title": "统计任务1", "category": "工作"})
    client.post("/tasks", json={"title": "统计任务2", "category": "学习"})

    resp = client.get("/stats/daily")
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_added"] >= 2


def test_health():
    """健康检查"""
    resp = client.get("/health")
    assert resp.json() == {"status": "ok"}
