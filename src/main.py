"""FastAPI 入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import ensure_data_dirs, API_HOST, API_PORT
from src.routers import tasks, subtasks, notes, detail, agenda, search, stats, recurrences
from src.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    ensure_data_dirs()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="日程待办系统", version="0.1.0", lifespan=lifespan)

# 注意: search 必须在 tasks 之前注册，否则 /tasks/search 会被 /tasks/{id} 拦截
app.include_router(search.router)
app.include_router(tasks.router)
app.include_router(subtasks.router)
app.include_router(notes.router)
app.include_router(detail.router)
app.include_router(agenda.router)
app.include_router(stats.router)
app.include_router(recurrences.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=API_HOST, port=API_PORT, reload=True)
