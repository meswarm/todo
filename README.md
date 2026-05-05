[语言-中文](README.md)
[Language-English](README_EN.md)

# Todo Matrix Agent

> Matrix-first 的个人待办代理。通过 Matrix 收发消息，LLM 负责解析意图与调用工具，任务数据使用本地 JSON 存储，媒体内容支持 R2 链接与本地下载。

## 核心能力

- 创建、查询、修改、完成任务
- 周期任务规则与按日期投影查询
- 晨间推送、晚间复盘、统一提醒
- Markdown + `r2://...` 媒体链接处理
- Matrix 运行时、工具调用、JSON 持久化

## 运行方式

当前运行路径为 **Matrix-first runtime**，不启动 FastAPI，不依赖 Webhook。

- `make run` 直接执行 `src.main -> src.app.main()`；`src.main` 仅为命令入口
- `src.app.run()` 完成：
  - `ensure_data_dirs()` 数据目录初始化
  - `TodoAgent` 启动（Matrix + LLM + 工具链）
  - `start_scheduler()` 启动定时任务
  - 信号驱动退出（`SIGINT`/`SIGTERM`）并清理关闭

## 安装

```bash
cp .env.example .env
make init
make run
```

如果不使用 make：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m src.main
```

## 配置（`.env`）

- `TODO_DATA_DIR`：任务与历史 JSON 存储目录（默认 `./db`）
- `TODO_DOWNLOADS_DIR`：媒体下载目录（默认 `./downloads`），按类别落盘到 `downloads/imgs|videos|audios|files`
- `TODO_SYSTEM_PROMPT`：系统提示词路径，默认 `./prompts/system_prompt.md`
- `TODO_SKILLS_DIR`：可选技能目录
- `MATRIX_HOMESERVER` / `MATRIX_USER` / `MATRIX_PASSWORD` / `MATRIX_ROOMS`：Matrix 客户端配置
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`：LLM 运行参数（用于推理与工具调用）
- `LLM_VISION_ENABLED`：`true/false`，开启后支持图片多模态理解
- `R2_ENDPOINT` / `R2_ACCESS_KEY` / `R2_SECRET_KEY` / `R2_BUCKET` / `R2_PUBLIC_URL`：R2 基础配置
- `R2_DOWNLOAD_IMAGES` / `R2_DOWNLOAD_VIDEOS` / `R2_DOWNLOAD_AUDIOS` / `R2_DOWNLOAD_FILES`：R2 下载开关，`true`/`false`
- `TODO_MORNING_HOUR` / `TODO_MORNING_MINUTE`：晨间任务扫描时间
- `TODO_EVENING_HOUR` / `TODO_EVENING_MINUTE`：晚间任务扫描时间
- `TODO_REMINDERS`：统一提醒分钟列表，例如 `10,5,2`

## 目录

```text
.
├── src/
│   ├── app.py              # 运行时入口
│   ├── agent.py            # Matrix + LLM + 工具编排
│   ├── matrix_client.py    # Matrix 客户端抽象
│   ├── llm_engine.py       # 推理与工具调用
│   ├── tool_registry.py    # Tool 注册
│   ├── media_store.py      # R2/本地媒体处理
│   ├── tools/              # 内置 todo 工具
│   ├── services/           # 任务域服务、通知汇总
│   └── scheduler/          # 定时任务
├── prompts/
│   └── system_prompt.md    # 系统提示词
├── tests/                  # 核心测试
├── .env.example
├── requirements.txt
├── Makefile
└── README_EN.md
```

## 运行日志

启动时打印基础日志；`make run` 默认进入持续监听状态。

## 测试

```bash
make test
```
