# 日程待办系统 (Todo API)

个人使用的轻量级日程待办管理系统，提供 REST API 和定时推送功能，通过 [Link 中间件](https://github.com/txl/link) 实现 AI 辅助的任务管理。

## 功能特性

- **任务管理** — 完整 CRUD、四态流转（pending → in_progress → completed/abandoned）
- **优先级模型** — 三维度评估（紧急度×重要性×难度）+ 预估耗时
- **子任务 & 依赖** — 一层子任务 + 任务依赖（拓扑排序）
- **灵活提醒** — 支持宽松（30分钟前）和卡点（5/2/1分钟前）两种模式
- **重复任务** — 支持每日/每周/每月/自定义间隔
- **详情文档** — Markdown 附件，支持图片路径、链接、详细步骤
- **关键词搜索** — 搜索活跃任务和历史记录
- **智能日程** — 依赖拓扑 + 优先级排序的日程视图
- **定时推送** — 早晨日程推送、晚间复盘推送、即时提醒
- **统计分析** — 日/周/月统计快照，支持 AI 分析

## 快速启动

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python -m src.main
# 服务运行在 http://localhost:8090
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TODO_DATA_DIR` | `./data` | 数据存储目录 |
| `TODO_HOST` | `0.0.0.0` | 监听地址 |
| `TODO_PORT` | `8090` | 监听端口 |
| `TODO_WEBHOOK_URL` | `http://localhost:9001/notify` | Webhook 推送目标 |
| `TODO_MORNING_HOUR` | `8` | 早晨推送时间（小时） |
| `TODO_EVENING_HOUR` | `21` | 晚间推送时间（小时） |

## 项目结构

```
todo/
├── src/
│   ├── config.py          # 配置管理
│   ├── main.py            # FastAPI 入口
│   ├── models/            # Pydantic 数据模型
│   │   ├── task.py        # 任务模型
│   │   ├── recurrence.py  # 重复规则模型
│   │   └── stats.py       # 统计模型
│   ├── storage/           # JSON 文件存储（带文件锁）
│   ├── services/          # 业务逻辑层
│   │   ├── task_service.py    # 任务 CRUD
│   │   ├── agenda_service.py  # 日程排序
│   │   └── webhook.py        # Webhook 推送
│   ├── routers/           # API 路由
│   │   ├── tasks.py       # 任务 CRUD API
│   │   ├── subtasks.py    # 子任务 API
│   │   ├── notes.py       # 备注 API
│   │   ├── detail.py      # 详情文档 API
│   │   ├── agenda.py      # 日程视图 API
│   │   ├── search.py      # 搜索 API
│   │   ├── stats.py       # 统计 API
│   │   └── recurrences.py # 重复任务 API
│   ├── scheduler/         # 定时调度
│   │   ├── engine.py      # APScheduler 引擎
│   │   ├── morning_push.py    # 早晨推送
│   │   ├── evening_push.py    # 晚间推送
│   │   ├── reminder_scan.py   # 提醒扫描
│   │   ├── overdue_scan.py    # 逾期扫描
│   │   ├── recurrence_gen.py  # 重复任务生成
│   │   └── stats_gen.py       # 统计生成
│   └── utils/             # 工具函数
├── tests/                 # 测试
├── link/                  # Link 中间件配置
│   ├── config-template.yaml   # 配置模板
│   └── todo-agent.yaml        # 待办助手配置
├── docs/plans/            # 设计文档
└── data/                  # 运行时数据（gitignored）
    ├── tasks.json         # 活跃任务
    ├── history.json       # 历史任务
    ├── recurrences.json   # 重复规则
    ├── docs/              # 详情 Markdown
    ├── files/             # 附件
    └── stats/             # 统计快照
```

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/tasks` | 创建任务 |
| `GET` | `/tasks` | 列表（支持筛选） |
| `GET` | `/tasks/{id}` | 获取详情 |
| `PUT` | `/tasks/{id}` | 更新任务 |
| `DELETE` | `/tasks/{id}` | 删除任务 |
| `PATCH` | `/tasks/{id}/status` | 变更状态 |
| `POST` | `/tasks/{id}/subtasks` | 添加子任务 |
| `POST` | `/tasks/{id}/notes` | 添加备注 |
| `PUT` | `/tasks/{id}/detail` | 更新详情文档 |
| `GET` | `/tasks/{id}/detail` | 获取详情文档 |
| `PUT` | `/tasks/{id}/reminders` | 设置提醒 |
| `PUT` | `/tasks/{id}/dependencies` | 设置依赖 |
| `GET` | `/tasks/search?q=关键词` | 搜索任务 |
| `GET` | `/agenda` | 日程视图 |
| `POST` | `/recurrences` | 创建重复规则 |
| `GET` | `/recurrences` | 列表重复规则 |
| `GET` | `/stats/daily` | 当日统计 |
| `GET` | `/stats/weekly?week=2026-W15` | 周统计 |
| `GET` | `/stats/monthly?month=2026-04` | 月统计 |

完整 API 文档：启动服务后访问 http://localhost:8090/docs

## 运行测试

```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

## 技术栈

- **Python 3.12** + **FastAPI** — REST API
- **Pydantic v2** — 数据模型验证
- **APScheduler** — 定时任务调度
- **httpx** — Webhook 推送
- **filelock** — 文件锁（并发安全）
- **JSON 文件存储** — 轻量级持久化
