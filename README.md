[语言-中文](README.md)
[Language-English](README_EN.md)

# 日程待办系统 (Todo API)

> 轻量级个人待办与日程服务：提供 REST API、JSON 持久化、定时调度与 Webhook 推送，可与 [Link 中间件](https://github.com/txl/link) 组合实现 AI 辅助管理。

适合需要自托管任务数据、又不想引入重型数据库的场景。默认配置从项目根目录的 `.env.example` / `.env` 读取，**应用代码中不硬编码监听端口**。

## 功能特性

- **任务管理** — 完整 CRUD、四态流转（pending → in_progress → completed/abandoned）
- **优先级模型** — 三维度评估（紧急度×重要性×难度）+ 预估耗时
- **子任务 & 依赖** — 一层子任务 + 任务依赖（拓扑排序）
- **灵活提醒** — 支持宽松（30 分钟前）和卡点（5/2/1 分钟前）两种模式
- **重复任务** — 支持每日/每周/每月/自定义间隔
- **详情文档** — Markdown 附件，支持图片路径、链接、详细步骤
- **关键词搜索** — 搜索活跃任务和历史记录
- **智能日程** — 依赖拓扑 + 优先级排序的日程视图
- **定时推送** — 早晨日程推送、晚间复盘推送、即时提醒
- **统计分析** — 日/周/月统计快照，便于复盘

## 技术栈


| 类别  | 技术                                   |
| --- | ------------------------------------ |
| 语言  | Python 3.12+                         |
| Web | FastAPI、Uvicorn                      |
| 数据  | Pydantic v2、JSON 文件存储（filelock）      |
| 调度  | APScheduler                          |
| 集成  | httpx（Webhook）、python-dotenv（`.env`） |


## 快速开始

### 前置要求

- Python 3.12+
- `make`（可选，用于统一命令）

### 安装与运行

```bash
git clone https://github.com/OWNER/REPO.git
cd REPO

make init
make run
```

将 `OWNER/REPO` 替换为你的 GitHub 用户/组织名与仓库名。默认监听端口见 `.env.example` 中的 `TODO_PORT`。

不使用 `make` 时：

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PYTHONPATH=. python -m src.main
```

说明：`make run`、`make test` **不会**自动创建虚拟环境；若未初始化，请先执行 `make init`。

### 配置 `.env`

项目会先加载 `.env.example`（仓库默认），再由 `.env` 覆盖（本地私有配置）。

```bash
cp .env.example .env
# 按需编辑 .env，勿将真实密钥或仅本机路径提交到 Git
```

`.env` 已列入 `.gitignore`。**不要将**真实 API 密钥、私有 URL 或本机绝对路径写入 README。

`link/todo-agent.yaml` 中的 REST 工具地址使用 `${TODO_PORT}`，需与待办 API 端口一致。启动 Link（`ltool`）前请在环境中导出与 `.env` 相同的 `TODO_PORT`，例如：`export TODO_PORT=48890`。

## 环境变量


| 变量                                          | 说明                                 |
| ------------------------------------------- | ---------------------------------- |
| `TODO_DATA_DIR`                             | 数据目录（默认 `./data`，已 gitignore）      |
| `TODO_HOST`                                 | 监听地址（见 `.env.example`）             |
| `TODO_PORT`                                 | 监听端口（见 `.env.example`）             |
| `TODO_WEBHOOK_URL`                          | Webhook 推送完整 URL（见 `.env.example`） |
| `TODO_MORNING_HOUR` / `TODO_MORNING_MINUTE` | 早晨推送时刻                             |
| `TODO_EVENING_HOUR` / `TODO_EVENING_MINUTE` | 晚间推送时刻                             |


具体默认值以 `.env.example` 为准。

## 项目结构

```text
.
├── .env.example          # 环境变量模板（可复制为 .env）
├── LICENSE
├── Makefile              # make init / run / test / clean
├── README.md / README_EN.md
├── requirements.txt
├── src/                  # 应用源码（FastAPI、调度、存储）
├── tests/                # pytest
├── link/                 # Link 接入示例（YAML；含占位符时请自行替换敏感信息）
├── docs/                 # 设计与计划文档
│   ├── plans/
│   └── superpowers/
└── data/                 # 运行时数据（默认 gitignore，勿提交）
```

本地媒体缓存目录 `media_cache/` 已加入 `.gitignore`，请勿将下载的媒体提交到仓库。

## API 概览


| 方法             | 路径                         | 说明                 |
| -------------- | -------------------------- | ------------------ |
| `POST`         | `/tasks`                   | 创建任务               |
| `GET`          | `/tasks`                   | 列表（支持筛选）           |
| `GET`          | `/tasks/{id}`              | 获取详情               |
| `PUT`          | `/tasks/{id}`              | 更新任务               |
| `DELETE`       | `/tasks/{id}`              | 删除任务               |
| `PATCH`        | `/tasks/{id}/status`       | 变更状态               |
| `POST`         | `/tasks/{id}/subtasks`     | 添加子任务              |
| `POST`         | `/tasks/{id}/notes`        | 添加备注               |
| `PUT` / `GET`  | `/tasks/{id}/detail`       | 更新 / 读取详情 Markdown |
| `PUT`          | `/tasks/{id}/reminders`    | 设置提醒               |
| `PUT`          | `/tasks/{id}/dependencies` | 设置依赖               |
| `GET`          | `/tasks/search?q=…`        | 搜索任务               |
| `GET`          | `/agenda`                  | 日程视图               |
| `POST` / `GET` | `/recurrences`             | 重复规则               |
| `GET`          | `/stats/daily` 等           | 统计                 |


完整 OpenAPI：启动后访问 `http://localhost:<TODO_PORT>/docs`（`<TODO_PORT>` 与 `.env` 一致）。

## 运行测试

```bash
make test
```

## 贡献指南

1. Fork 本仓库
2. 创建分支：`git checkout -b feat/your-feature`
3. 提交：`git commit -m 'feat: describe change'`
4. 推送：`git push origin feat/your-feature`
5. 发起 Pull Request

## 安全提示（发布前必读）

- 若 `link/todo-agent.yaml` 中含 Matrix 账号、房间 ID 等，**公共仓库**发布前请改为占位符或改用私有配置，并轮换已泄露的凭证。  
- 确认未将 `.env`、`data/`、`media_cache/` 或任何密钥文件加入提交。

## 许可证

MIT — 详见 [LICENSE](LICENSE)。