# 日程待办系统 — 设计文档

> 日期: 2026-04-12
> 状态: 待审批

## 概述

个人日程待办系统，提供 REST API 和定时推送服务。通过 Link 中间件与用户交互（自然语言 → Link → 本系统 API），本项目不涉及 AI/LLM 逻辑，仅提供纯代码实现的 API 服务及定时推送机制。

**架构边界：**
- **本项目负责**：API 服务、数据存储、定时器推送、逾期标记、统计生成
- **Link 中间件负责**：自然语言理解、工具调用、消息润色、推送给用户

## 技术选型

| 项目 | 选择 |
|------|------|
| 语言 | Python |
| Web 框架 | FastAPI |
| 定时任务 | APScheduler |
| 数据存储 | JSON 文件 |
| 用户模式 | 单用户 |

## 一、数据模型

### 1.1 任务（Task）

```json
{
    "id": "task_20260412_001",
    "title": "准备马拉松比赛",
    "description": "下月的半程马拉松，需要制定训练计划并购买装备",
    "status": "pending",
    "category": "健康",
    "tags": ["运动", "马拉松"],

    "urgency": 2,
    "importance": 3,
    "difficulty": 2,
    "estimated_minutes": 60,

    "timing_mode": "flexible",

    "created_at": "2026-04-12T13:00:00",
    "updated_at": "2026-04-12T13:00:00",
    "deadline": "2026-05-15T08:00:00",
    "scheduled_at": "2026-04-20T09:00:00",

    "reminders": [
        {"type": "before_deadline", "minutes": 1440},
        {"type": "fixed_time", "time": "2026-05-14T20:00:00"}
    ],

    "recurrence_id": null,

    "depends_on": ["task_20260410_003"],

    "detail_doc": "data/docs/task_20260412_001.md",

    "subtasks": [
        {"id": "sub_001", "title": "制定训练计划", "status": "completed"},
        {"id": "sub_002", "title": "购买运动装备", "status": "pending"}
    ],

    "notes": [
        {"time": "2026-04-12T14:00:00", "content": "选择了本地半马赛事"},
        {"time": "2026-04-15T20:00:00", "content": "完成首次5公里训练，配速6分半"}
    ],

    "completion": {
        "completed_at": null,
        "actual_minutes": null,
        "summary": null
    },

    "is_overdue": false
}
```

### 1.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 自动生成 | 格式: `task_YYYYMMDD_NNN` |
| `title` | string | ✅ | 任务标题 |
| `description` | string | ❌ | 详细描述 |
| `status` | enum | 自动 | `pending` → `in_progress` → `completed` / `abandoned` |
| `category` | string | ✅ | 主分类（单选） |
| `tags` | string[] | ❌ | 自由标签（多个） |
| `urgency` | int(1-3) | ❌ 默认2 | 紧急度：1低 2中 3高 |
| `importance` | int(1-3) | ❌ 默认2 | 重要性：1低 2中 3高 |
| `difficulty` | int(1-3) | ❌ 默认2 | 难度：1低 2中 3高 |
| `estimated_minutes` | int | ❌ | 预估耗时（分钟） |
| `timing_mode` | enum | ❌ 默认flexible | `flexible`（宽松）/ `time_critical`（卡点） |
| `created_at` | datetime | 自动 | 创建时间 |
| `updated_at` | datetime | 自动 | 最后更新时间 |
| `deadline` | datetime | ❌ | 截止时间 |
| `scheduled_at` | datetime | ❌ | 计划开始时间 |
| `reminders` | array | ❌ | 提醒规则列表 |
| `recurrence_id` | string | ❌ | 关联的重复规则ID |
| `depends_on` | string[] | ❌ | 依赖的任务ID列表 |
| `detail_doc` | string | ❌ | 任务详情 Markdown 文件路径（图片、链接、详细步骤等） |
| `subtasks` | array | ❌ | 子任务列表（一层） |
| `notes` | array | ❌ | 备注评论流（带时间戳） |
| `completion` | object | ❌ | 完成信息（完成/放弃时填写） |
| `is_overdue` | bool | 自动 | 系统根据 deadline 自动标记 |

### 1.3 状态流转

```
pending ──→ in_progress ──→ completed
   │              │
   │              └──────→ abandoned
   │
   └──────────────────────→ abandoned
```

- 状态变更时自动更新 `updated_at`
- 变为 `completed` / `abandoned` 时填写 `completion` 信息并迁移到历史

### 1.4 提醒类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `before_deadline` | 截止前 N 分钟 | `{"type": "before_deadline", "minutes": 30}` |
| `fixed_time` | 指定时间点 | `{"type": "fixed_time", "time": "2026-04-12T09:00:00"}` |

**timing_mode 自动默认提醒：**

| 模式 | 自动提醒 |
|------|---------|
| `flexible` | 截止前 30 分钟 |
| `time_critical` | 截止前 5 分钟 + 2 分钟 + 1 分钟 |

用户/AI 可在 `reminders` 中额外追加自定义提醒，不覆盖自动提醒。

### 1.5 重复规则（Recurrence）

```json
{
    "id": "rec_001",
    "title": "每日运动",
    "task_template": {
        "title": "运动30分钟",
        "category": "健康",
        "tags": ["运动", "日常"],
        "urgency": 1,
        "importance": 3,
        "difficulty": 1,
        "estimated_minutes": 30,
        "timing_mode": "flexible"
    },
    "pattern": "interval",
    "interval_days": 1,
    "week_days": null,
    "month_day": null,
    "time_of_day": "09:00",
    "start_date": "2026-04-12",
    "end_date": "2026-06-30",
    "enabled": true,
    "last_generated": "2026-04-12"
}
```

| pattern | 说明 | 配合字段 |
|---------|------|---------|
| `daily` | 每天 | `time_of_day` |
| `weekly` | 每周指定日 | `week_days` (如 [1,3,5] 周一三五), `time_of_day` |
| `monthly` | 每月指定日 | `month_day` (如 15), `time_of_day` |
| `interval` | 每隔N天 | `interval_days`, `time_of_day` |

## 二、存储结构

```
data/
├── tasks.json              # 活跃任务（pending + in_progress）
├── history.json            # 历史任务（completed + abandoned）
├── recurrences.json        # 重复规则模板
├── docs/                   # 任务详情 Markdown 文件
│   ├── task_20260412_001.md
│   └── task_20260412_002.md
├── files/                  # 附件（图片等二进制文件）
│   └── task_20260412_001/
│       └── 截图.png
└── stats/
    ├── weekly/
    │   └── 2026-W15.json   # 周统计快照
    └── monthly/
        └── 2026-04.json    # 月统计快照
```

**设计要点：**
- 活跃与历史分离：`tasks.json` 仅保留进行中任务，保持精简
- 任务完成/放弃时自动迁移到 `history.json`
- `notes` 用于轻量快捷备注（一两句话），`detail_doc` 用于丰富的详情文档（图片、链接、执行步骤等）
- 统计快照由定时器生成，避免每次查询遍历历史
- 所有 JSON 文件操作使用文件锁确保并发安全

## 三、API 设计

### 3.1 任务 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks` | 创建任务 |
| GET | `/tasks` | 查询任务列表 |
| GET | `/tasks/{id}` | 获取任务详情 |
| PUT | `/tasks/{id}` | 更新任务 |
| DELETE | `/tasks/{id}` | 删除任务 |
| PATCH | `/tasks/{id}/status` | 变更状态 |

**GET `/tasks` 查询参数：**

| 参数 | 说明 | 示例 |
|------|------|------|
| `status` | 按状态筛选 | `?status=pending` |
| `category` | 按分类筛选 | `?category=工作` |
| `tags` | 按标签筛选（逗号分隔） | `?tags=运动,日常` |
| `is_overdue` | 筛选逾期任务 | `?is_overdue=true` |
| `from` / `to` | 按截止时间范围 | `?from=2026-04-12&to=2026-04-19` |

### 3.2 子任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks/{id}/subtasks` | 添加子任务 |
| PATCH | `/tasks/{id}/subtasks/{sub_id}` | 更新子任务 |
| DELETE | `/tasks/{id}/subtasks/{sub_id}` | 删除子任务 |

### 3.3 备注

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks/{id}/notes` | 追加备注 |
| GET | `/tasks/{id}/notes` | 获取任务所有备注 |

### 3.4 任务详情文档

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/tasks/{id}/detail` | 创建/更新详情 Markdown |
| GET | `/tasks/{id}/detail` | 获取详情 Markdown 内容 |

### 3.5 提醒与依赖

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/tasks/{id}/reminders` | 设置提醒规则 |
| PUT | `/tasks/{id}/dependencies` | 设置依赖关系 |

### 3.6 搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks/search?q=关键词` | 关键词搜索（标题+描述+备注，含历史） |
| GET | `/tasks/search?q=关键词&scope=active` | 仅搜索活跃任务 |
| GET | `/tasks/search?q=关键词&scope=history` | 仅搜索历史任务 |

### 3.7 日程视图（Agenda）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/agenda?range=today` | 今日日程 |
| GET | `/agenda?range=7d` | 未来7天 |
| GET | `/agenda?range=30d` | 未来30天 |
| GET | `/agenda?from=&to=` | 自定义日期区间 |

**排序规则（优先级从高到低）：**
1. 依赖关系拓扑排序（被依赖的任务排前面）
2. 逾期任务优先
3. `time_critical` 任务优先
4. 紧急度 × 重要性 综合得分降序
5. 截止时间升序（先到期的排前面）

**返回格式：**
```json
{
    "date": "2026-04-12",
    "summary": {
        "total": 8,
        "pending": 5,
        "in_progress": 2,
        "overdue": 1,
        "time_critical": 1
    },
    "tasks": [...],
    "upcoming_important": [...]
}
```

### 3.8 统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stats/daily?date=2026-04-12` | 当日统计 |
| GET | `/stats/weekly?week=2026-W15` | 周统计 |
| GET | `/stats/monthly?month=2026-04` | 月统计 |

**统计数据包含：**
- 完成率（完成数 / 总数）
- 拖延率（逾期完成数 / 总完成数）
- 放弃率
- 分类分布（工作/学习/生活等各占比）
- 平均实际耗时 vs 预估耗时（准确度）
- 难度分布

### 3.9 重复任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/recurrences` | 创建重复规则 |
| GET | `/recurrences` | 查看所有重复规则 |
| PUT | `/recurrences/{id}` | 修改重复规则 |
| DELETE | `/recurrences/{id}` | 取消重复规则 |

## 四、定时推送机制

### 4.1 定时器调度表

| 任务 | 频率 | 说明 |
|------|------|------|
| 重复任务生成 | 每日 00:30 | 扫描 recurrences，生成当日任务实例 |
| 早晨推送 | 每日 08:00 | 今日日程 + 未来7天重要事项 |
| 晚间推送 | 每日 21:00 | 当日复盘 + 逾期处理提醒 |
| 即时提醒扫描 | 每 60 秒 | 检查 reminder 触发、截止前提醒 |
| 卡点任务加速扫描 | 每 30 秒 | 仅当存在 15 分钟内即将触发的 `time_critical` 任务时激活 |
| 逾期扫描 | 每小时 | 超过 deadline 的任务标记 `is_overdue=true` |
| 周统计生成 | 每周日 23:00 | 生成本周统计快照 |
| 月统计生成 | 每月最后一天 23:00 | 生成本月统计快照 |

### 4.2 Webhook 推送格式

推送目标：Link 中间件的 webhook endpoint

**早晨推送 (morning_agenda)：**
```json
{
    "type": "morning_agenda",
    "timestamp": "2026-04-12T08:00:00",
    "data": {
        "today_tasks": [
            {
                "id": "task_001",
                "title": "完成周报",
                "deadline": "2026-04-12T18:00:00",
                "urgency": 3,
                "importance": 2,
                "difficulty": 1,
                "estimated_minutes": 30,
                "timing_mode": "flexible",
                "depends_on": [],
                "subtasks_progress": "1/3"
            }
        ],
        "overdue_tasks": [...],
        "upcoming_important": [
            {
                "id": "task_010",
                "title": "马拉松比赛",
                "deadline": "2026-05-15T08:00:00",
                "days_until": 33
            }
        ],
        "stats_summary": {
            "today_total": 5,
            "today_pending": 3,
            "today_in_progress": 2,
            "overdue_count": 1,
            "time_critical_count": 0
        }
    }
}
```

**晚间推送 (evening_review)：**
```json
{
    "type": "evening_review",
    "timestamp": "2026-04-12T21:00:00",
    "data": {
        "completed_today": [...],
        "incomplete_today": [...],
        "overdue_tasks": [
            {
                "id": "task_003",
                "title": "提交报告",
                "deadline": "2026-04-12T17:00:00",
                "overdue_hours": 4,
                "options": ["continue_tomorrow", "abandon", "simplify"]
            }
        ],
        "daily_stats": {
            "completed": 3,
            "abandoned": 0,
            "new_added": 2,
            "completion_rate": 0.6
        }
    }
}
```

**即时提醒 (task_reminder)：**
```json
{
    "type": "task_reminder",
    "timestamp": "2026-04-12T14:30:00",
    "data": {
        "task": {
            "id": "task_005",
            "title": "抢购演唱会门票",
            "deadline": "2026-04-12T15:00:00",
            "timing_mode": "time_critical",
            "minutes_until": 30
        },
        "reminder_reason": "time_critical_approaching"
    }
}
```

## 五、项目结构

```
todo/
├── link/                       # Link 中间件配置
│   └── config-template.yaml
├── docs/
│   └── plans/
│       └── 2026-04-12-todo-system-design.md
├── src/
│   ├── main.py                 # FastAPI 入口 + 启动调度器
│   ├── config.py               # 配置管理（端口、推送时间、webhook地址等）
│   ├── models/
│   │   ├── task.py             # Task 数据模型 (Pydantic)
│   │   ├── recurrence.py       # 重复规则模型
│   │   └── stats.py            # 统计数据模型
│   ├── storage/
│   │   ├── json_store.py       # JSON 文件读写（带文件锁）
│   │   └── migration.py        # 任务迁移（活跃 → 历史）
│   ├── routers/
│   │   ├── tasks.py            # 任务 CRUD API
│   │   ├── subtasks.py         # 子任务 API
│   │   ├── notes.py            # 备注 API
│   │   ├── agenda.py           # 日程视图 API
│   │   ├── stats.py            # 统计 API
│   │   ├── recurrences.py      # 重复任务 API
│   │   └── search.py           # 搜索 API
│   ├── scheduler/
│   │   ├── engine.py           # APScheduler 调度引擎
│   │   ├── morning_push.py     # 早晨推送
│   │   ├── evening_push.py     # 晚间推送
│   │   ├── reminder_scan.py    # 即时提醒扫描
│   │   ├── overdue_scan.py     # 逾期扫描
│   │   ├── recurrence_gen.py   # 重复任务生成
│   │   └── stats_gen.py        # 统计快照生成
│   ├── services/
│   │   ├── task_service.py     # 任务业务逻辑
│   │   ├── agenda_service.py   # 日程排序逻辑（依赖拓扑+优先级）
│   │   └── webhook.py          # Webhook 推送客户端
│   └── utils/
│       ├── id_gen.py           # ID 生成器
│       └── time_utils.py       # 时间工具
├── data/                       # 数据目录（运行时生成）
│   ├── tasks.json
│   ├── history.json
│   ├── recurrences.json
│   └── stats/
├── requirements.txt
└── README.md
```

## 六、Link 中间件配置要点

本项目需提供 `link/todo-agent.yaml` 配置文件，核心要素：

- **prompt**: 日程助手的系统提示词，引导 LLM 合理使用各 API
- **context**: 预注入今日日程摘要（调用 `/agenda?range=today`）
- **tools**: 所有 API 注册为 Link 工具（type: api）
- **webhook**: 接收定时推送的 endpoint 配置
- **skills**: 可选的 Skill 文件，教 LLM 任务管理最佳实践

## 七、后续可扩展方向（不在第一版范围内）

- 与个人知识库 RAG 集成（通过知识库 API 搜索历史经验）
- 任务优先级 AI 自动评估（通过 Link 中间件实现）
- 日历视图导出（iCal 格式）
- 番茄钟集成（任务执行计时）
