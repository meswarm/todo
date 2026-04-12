"""应用配置管理"""
from pathlib import Path
import os

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录
DATA_DIR = Path(os.getenv("TODO_DATA_DIR", str(BASE_DIR / "data")))
TASKS_FILE = DATA_DIR / "tasks.json"
HISTORY_FILE = DATA_DIR / "history.json"
RECURRENCES_FILE = DATA_DIR / "recurrences.json"
DOCS_DIR = DATA_DIR / "docs"
FILES_DIR = DATA_DIR / "files"
STATS_DIR = DATA_DIR / "stats"

# API 服务
API_HOST = os.getenv("TODO_HOST", "0.0.0.0")
API_PORT = int(os.getenv("TODO_PORT", "8090"))

# Webhook 推送目标
WEBHOOK_URL = os.getenv("TODO_WEBHOOK_URL", "http://localhost:9001/notify")

# 推送时间配置
MORNING_PUSH_HOUR = int(os.getenv("TODO_MORNING_HOUR", "8"))
MORNING_PUSH_MINUTE = int(os.getenv("TODO_MORNING_MINUTE", "0"))
EVENING_PUSH_HOUR = int(os.getenv("TODO_EVENING_HOUR", "21"))
EVENING_PUSH_MINUTE = int(os.getenv("TODO_EVENING_MINUTE", "0"))


def ensure_data_dirs():
    """创建所有数据目录"""
    for d in [DATA_DIR, DOCS_DIR, FILES_DIR, STATS_DIR,
              STATS_DIR / "weekly", STATS_DIR / "monthly"]:
        d.mkdir(parents=True, exist_ok=True)
    # 初始化空 JSON 文件
    for f in [TASKS_FILE, HISTORY_FILE, RECURRENCES_FILE]:
        if not f.exists():
            f.write_text("[]")
