# Todo Matrix Agent

[English](README.en.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Matrix](https://img.shields.io/badge/Matrix-bot-blue)
![Storage](https://img.shields.io/badge/storage-local_JSON-green)
![License](https://img.shields.io/badge/license-MIT-green)

Todo Matrix Agent 是一个 Matrix-first 的个人待办机器人。它通过 Matrix 收发消息，使用大模型处理创建、修改、周期规则等复杂意图，用纯代码处理明确快捷指令、提醒、早午晚报和 Markdown 表格展示。任务、历史、周期规则和提醒去重状态默认保存在本地 JSON 文件中。

## 功能

- 自然语言创建和修改任务，支持图片、语音、视频、文件等 R2 媒体链接原样写入详情。
- 固定快捷指令不经过大模型：`list today`、`list next`、`list history N`、`delete ID`、`complete ID`。
- 支持一次性任务和周期任务规则，周期规则可以创建、修改、删除。
- 支持准点任务和宽泛时段任务：上午、下午、晚上。
- 准点任务按 `TODO_REMINDERS` 提前提醒，宽泛时段任务按配置的时段锚点合并提醒。
- 每日早报和午报推送今日任务，晚报推送明日任务。
- 主动通知消息带 `com.talk.kind=notification` 元数据，方便 Matrix 客户端高亮展示。
- 本地历史归档，支持 `list history N` 查看过去 N 天任务。

## 环境要求

- Python 3.10 或更新版本。当前项目已在 Python 3.12 环境下运行和测试。
- 一个可用的 Matrix 账号和房间。
- 一个兼容 OpenAI Chat Completions 的大模型服务。
- 可选：Cloudflare R2 或兼容对象存储，用于媒体链接和下载。

## 安装与配置

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，至少需要填写 Matrix 和 LLM 配置：

```bash
MATRIX_HOMESERVER=https://matrix.example.com
MATRIX_USER=@todo-bot:example.com
MATRIX_PASSWORD=change-me
MATRIX_ROOMS=!room-id:example.com
LLM_BASE_URL=https://example.com/compatible-mode/v1
LLM_API_KEY=change-me
LLM_MODEL=model-name
```

启动：

```bash
make run
```

不使用 Makefile 时：

```bash
PYTHONPATH=. .venv/bin/python -m src.main
```

## 配置项

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TODO_BASE_DIR` | `.` | 相对路径解析基准目录 |
| `TODO_DATA_DIR` | `./db` | 任务、历史、周期规则和提醒状态目录 |
| `TODO_DOWNLOADS_DIR` | `./downloads` | 媒体下载目录 |
| `TODO_SYSTEM_PROMPT` | `./prompts/system_prompt.md` | 系统提示词路径 |
| `TODO_SKILLS_DIR` | 空 | 可选技能目录 |
| `TODO_CONTEXT_CELL_MAX_CHARS` | `300` | 表格单元格最大展示长度 |
| `MATRIX_HOMESERVER` | 示例值 | Matrix homeserver |
| `MATRIX_USER` | 示例值 | Matrix 机器人账号 |
| `MATRIX_PASSWORD` | `change-me` | Matrix 账号密码 |
| `MATRIX_ROOMS` | 示例值 | 允许响应的房间，逗号分隔 |
| `MATRIX_TYPING_ENABLED` | `true` | 是否发送 typing 状态 |
| `MATRIX_TYPING_TIMEOUT_MS` | `30000` | typing 超时时间 |
| `LLM_BASE_URL` | 示例值 | OpenAI 兼容接口地址 |
| `LLM_API_KEY` | `change-me` | 大模型 API Key |
| `LLM_MODEL` | 示例值 | 模型名称 |
| `LLM_TEMPERATURE` | `0.7` | 模型温度 |
| `LLM_MAX_HISTORY` | `20` | 对话历史条数 |
| `LLM_ENABLE_THINKING` | `false` | 是否启用模型 thinking 参数 |
| `LLM_VISION_ENABLED` | `false` | 是否启用图片多模态理解 |
| `R2_ENDPOINT` | 空 | R2 或兼容对象存储 endpoint |
| `R2_ACCESS_KEY` | 空 | R2 access key |
| `R2_SECRET_KEY` | 空 | R2 secret key |
| `R2_BUCKET` | `todo-media` | R2 bucket |
| `R2_PUBLIC_URL` | 空 | R2 公开访问 URL |
| `R2_DOWNLOAD_IMAGES` | `true` | 是否下载图片 |
| `R2_DOWNLOAD_VIDEOS` | `true` | 是否下载视频 |
| `R2_DOWNLOAD_AUDIOS` | `true` | 是否下载音频 |
| `R2_DOWNLOAD_FILES` | `true` | 是否下载文件 |
| `TODO_MORNING_HOUR` / `TODO_MORNING_MINUTE` | `7` / `0` | 早报时间，推送今日任务 |
| `TODO_NOON_HOUR` / `TODO_NOON_MINUTE` | `12` / `0` | 午报时间，推送今日任务 |
| `TODO_EVENING_HOUR` / `TODO_EVENING_MINUTE` | `23` / `0` | 晚报时间，推送明日任务 |
| `TODO_REMINDERS` | `10,5,2` | 准点任务提前提醒分钟数 |
| `TODO_REMINDER_MIN_LEAD_SECONDS` | `30` | 距离开始时间过近时不再补发提醒 |
| `TODO_SLOT_MORNING_TIME` | `08:00` | 上午宽泛任务提醒锚点 |
| `TODO_SLOT_AFTERNOON_TIME` | `14:00` | 下午宽泛任务提醒锚点 |
| `TODO_SLOT_EVENING_TIME` | `18:00` | 晚上宽泛任务提醒锚点 |

## 使用方法

常用快捷指令：

| 指令 | 行为 |
| --- | --- |
| `list today` | 直接返回今日任务 Markdown 表格 |
| `list next` | 返回明日任务、后天及以后 active 非周期任务、周期任务规则 |
| `list history 2` | 按日期返回过去 2 天历史任务 |
| `delete 26053101` | 删除真实任务 |
| `delete rec_20260428_001` | 删除周期任务规则 |
| `complete 26053101` | 标记今日任务完成，列表开始时间列显示 `✅` |

自然语言示例：

```text
今天晚上买菜
明天下午去超市
今天 20:00 买榴莲
把 26053108 改到明天上午
把每日铲屎喂粮改成每天上午
```

时间语义：

- 用户给出具体时间点时，任务是准点任务，例如 `05-31 20:00`。
- 用户只说上午、下午、晚上时，任务是宽泛时段任务，例如 `05-31 下午`。
- 用户没有说清楚时间点或时段时，大模型应追问上午、下午还是晚上。

## 开发

```bash
make test
```

或者直接运行：

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/ -m "not api" -v
```

目录结构：

```text
.
├── src/
│   ├── app.py              # 运行时入口
│   ├── agent.py            # Matrix + LLM + 工具编排
│   ├── matrix_client.py    # Matrix 客户端封装
│   ├── llm_engine.py       # OpenAI 兼容推理和工具调用
│   ├── media_store.py      # R2/本地媒体处理
│   ├── tools/              # Todo 工具定义
│   ├── services/           # 任务服务、通知队列、业务日逻辑
│   └── scheduler/          # 周期生成、提醒、早午晚报
├── prompts/
│   └── system_prompt.md
├── tests/
├── .env.example
├── requirements.txt
└── Makefile
```

## 隐私与安全

- `.env`、本地 `db/`、`downloads/`、虚拟环境、缓存和临时文件不应提交。
- `.env.example` 只保留占位符和安全默认值。
- 如果真实 Matrix 密码、LLM Key、R2 Key 曾经提交到公开历史，请立即轮换对应密钥。
- R2 媒体链接会进入任务详情，用于客户端渲染；不要在公共仓库提交包含个人媒体链接的本地数据文件。

## 许可证

本项目使用 [MIT License](LICENSE)。
