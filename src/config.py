"""应用配置管理"""
from pathlib import Path
import os

from dotenv import load_dotenv

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 先载入仓库默认（.env.example），再由本地 .env 覆盖（不在代码中写死端口）
load_dotenv(BASE_DIR / ".env.example")
load_dotenv(BASE_DIR / ".env", override=True)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise RuntimeError(
            f"缺少环境变量 {name}。请检查项目根目录的 .env.example 是否存在，"
            f"并执行 cp .env.example .env 后按需修改。"
        )
    return value


# 数据目录
DATA_DIR = Path(os.getenv("TODO_DATA_DIR", str(BASE_DIR / "data")))
TASKS_FILE = DATA_DIR / "tasks.json"
HISTORY_FILE = DATA_DIR / "history.json"
RECURRENCES_FILE = DATA_DIR / "recurrences.json"
DOCS_DIR = DATA_DIR / "docs"
FILES_DIR = DATA_DIR / "files"
STATS_DIR = DATA_DIR / "stats"

# API 服务（端口仅来自环境变量 / .env.example）
API_HOST = _require_env("TODO_HOST")
API_PORT = int(_require_env("TODO_PORT"))

# Webhook 推送目标（完整 URL，含主机与端口，由环境配置）
WEBHOOK_URL = _require_env("TODO_WEBHOOK_URL")

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
