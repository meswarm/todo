"""FastAPI 入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.config import ensure_data_dirs, API_HOST, API_PORT


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    ensure_data_dirs()
    yield


app = FastAPI(title="日程待办系统", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=API_HOST, port=API_PORT, reload=True)
