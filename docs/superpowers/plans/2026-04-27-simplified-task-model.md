# Simplified Task Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current overgrown todo schema with a compact personal-task model, keeping recurring tasks as separate rules and adding business-day archival plus reminder-state persistence.

**Architecture:** `tasks.json` stores all active and not-yet-archived task instances, including future one-off tasks and today’s generated recurring instances. `recurrences.json` stores recurring rules only. `history.json` receives task instances at the 02:00 business-day boundary. `reminder_state.json` stores fired reminder keys so restarts do not resend reminders.

**Tech Stack:** Python 3.12, Pydantic v2, JSON storage with `JsonStore`, APScheduler, Matrix runtime, OpenAI-compatible tool calling.

---

## File Structure

- Modify `src/models/task.py`: replace legacy task/status/update models with the simplified task instance model.
- Modify `src/models/recurrence.py`: simplify recurring task templates to match the new task fields.
- Modify `src/models/__init__.py`: export only the current models.
- Modify `src/services/task_service.py`: replace legacy CRUD/status flow with simplified create/update/complete/archive/query helpers.
- Modify `src/services/agenda_service.py`: sort and filter by business day, `scheduled_at`, `time_mode`, and `difficulty`.
- Modify `src/tools/todo_tools.py`: expose only simplified tools and schemas to the LLM.
- Modify `src/context.py`: render current business-day tasks, future one-off tasks, and recurrence rules with compact display markers.
- Modify `src/scheduler/reminder_scan.py`: compute reminders from `scheduled_at + time_mode`, persist fired reminder keys.
- Modify `src/scheduler/recurrence_gen.py`: generate current business-day instances from recurrence rules after 02:00.
- Modify `src/scheduler/engine.py`: schedule archive/generate jobs around the 02:00 business-day boundary.
- Modify `src/scheduler/morning_push.py`, `src/scheduler/evening_push.py`, `src/scheduler/overdue_scan.py`, `src/scheduler/stats_gen.py`: either simplify or remove old-field logic.
- Modify `src/agent.py`: update notification formatting for the simplified fields.
- Modify `prompts/system_prompt.md`: describe the simplified task model, display rules, flexible scheduling, recurring-task rules, and query decision boundaries.
- Modify tests under `tests/`: update model, service, context, tool, scheduler, and prompt tests to the new model.

---

## Final Data Model

Task instance:

```json
{
  "id": "task_20260427_001",
  "title": "开会",
  "status": "incomplete",
  "difficulty": 1,
  "time_mode": "time_critical",
  "scheduled_at": "2026-04-27T21:00:00",
  "created_at": "2026-04-27T19:40:48",
  "completed_at": null,
  "detail": "今晚 9 点开会",
  "completion_summary": "",
  "recurrence_id": null
}
```

Recurring rule:

```json
{
  "id": "rec_20260427_001",
  "title": "每日运动",
  "enabled": true,
  "pattern": "daily",
  "interval_days": null,
  "week_days": null,
  "month_day": null,
  "time_of_day": "18:00",
  "start_date": "2026-04-27",
  "end_date": null,
  "template": {
    "title": "运动",
    "difficulty": 1,
    "time_mode": "flexible",
    "detail": "每天运动 30 分钟"
  },
  "last_generated_for": "2026-04-27"
}
```

Reminder state:

```json
{
  "task_20260427_001:10": "2026-04-27T20:50:00",
  "task_20260427_001:5": "2026-04-27T20:55:00"
}
```

Display rules:

- `completed` -> `✅`
- `incomplete` -> `➖`
- `time_critical` -> `🟣🟣🟣`
- `flexible` -> `difficulty` red stars, `0..3`: none, `🔴`, `🔴🔴`, `🔴🔴🔴`

Business-day rule:

- Current business day starts at `02:00`.
- `00:00` through `01:59:59` still belongs to the previous business day.
- Archive the previous business day at `02:00`, then generate the new business day’s recurring task instances.

---

## Task 1: Replace Task Models

**Files:**
- Modify `src/models/task.py`
- Modify `src/models/__init__.py`
- Test `tests/test_models.py`

- [ ] **Step 1: Rewrite model tests for simplified fields**

Replace task model expectations with:

```python
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.task import Task, TaskCreate, TaskStatus, TimeMode


def test_task_create_defaults_to_incomplete_flexible_task():
    task = TaskCreate(
        title="写总结",
        difficulty=2,
        scheduled_at=datetime(2026, 4, 28, 10, 30),
        detail="整理重构记录",
    )

    assert task.status == TaskStatus.INCOMPLETE
    assert task.time_mode == TimeMode.FLEXIBLE
    assert task.completion_summary == ""
    assert task.recurrence_id is None


def test_task_title_is_short():
    with pytest.raises(ValidationError):
        TaskCreate(
            title="这是一个明显超过十个字的任务标题",
            difficulty=1,
            scheduled_at=datetime(2026, 4, 28, 10, 30),
            detail="x",
        )


def test_difficulty_allows_zero_to_three():
    TaskCreate(title="散步", difficulty=0, scheduled_at=datetime(2026, 4, 28, 10, 30))
    with pytest.raises(ValidationError):
        TaskCreate(title="bad", difficulty=4, scheduled_at=datetime(2026, 4, 28, 10, 30))
```

- [ ] **Step 2: Run model tests and confirm failure**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_models.py -v
```

Expected: failures because the simplified models do not exist yet.

- [ ] **Step 3: Implement simplified models**

Replace legacy task models with:

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    INCOMPLETE = "incomplete"
    COMPLETED = "completed"


class TimeMode(str, Enum):
    FLEXIBLE = "flexible"
    TIME_CRITICAL = "time_critical"


class Task(BaseModel):
    id: str
    title: str = Field(max_length=10)
    status: TaskStatus = TaskStatus.INCOMPLETE
    difficulty: int = Field(default=1, ge=0, le=3)
    time_mode: TimeMode = TimeMode.FLEXIBLE
    scheduled_at: datetime
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    detail: str = ""
    completion_summary: str = ""
    recurrence_id: Optional[str] = None


class TaskCreate(BaseModel):
    title: str = Field(max_length=10)
    status: TaskStatus = TaskStatus.INCOMPLETE
    difficulty: int = Field(default=1, ge=0, le=3)
    time_mode: TimeMode = TimeMode.FLEXIBLE
    scheduled_at: datetime
    detail: str = ""
    completion_summary: str = ""
    recurrence_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=10)
    status: Optional[TaskStatus] = None
    difficulty: Optional[int] = Field(default=None, ge=0, le=3)
    time_mode: Optional[TimeMode] = None
    scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    detail: Optional[str] = None
    completion_summary: Optional[str] = None
    recurrence_id: Optional[str] = None


class TaskComplete(BaseModel):
    completion_summary: str = ""
    completed_at: Optional[datetime] = None
```

- [ ] **Step 4: Update exports**

`src/models/__init__.py` should export `Task`, `TaskCreate`, `TaskUpdate`, `TaskComplete`, `TaskStatus`, `TimeMode`, plus recurrence and stats models that still exist.

- [ ] **Step 5: Run model tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_models.py -v
```

Expected: PASS.

---

## Task 2: Simplify Task Service and Business-Day Helpers

**Files:**
- Modify `src/services/task_service.py`
- Create `src/services/business_day.py`
- Test `tests/test_task_service.py`

- [ ] **Step 1: Add business-day tests**

Create `tests/test_task_service.py` with tests for:

```python
from datetime import datetime

from src.services.business_day import business_date, business_day_range


def test_business_date_before_2am_belongs_to_previous_day():
    assert business_date(datetime(2026, 4, 28, 1, 30)).isoformat() == "2026-04-27"


def test_business_date_after_2am_belongs_to_current_day():
    assert business_date(datetime(2026, 4, 28, 2, 0)).isoformat() == "2026-04-28"


def test_business_day_range_starts_at_2am():
    start, end = business_day_range(datetime(2026, 4, 28, 12, 0).date())
    assert start.isoformat() == "2026-04-28T02:00:00"
    assert end.isoformat() == "2026-04-29T01:59:59.999999"
```

- [ ] **Step 2: Implement `src/services/business_day.py`**

```python
from __future__ import annotations

from datetime import date, datetime, time, timedelta

BUSINESS_DAY_START_HOUR = 2


def business_date(now: datetime | None = None) -> date:
    current = now or datetime.now()
    if current.hour < BUSINESS_DAY_START_HOUR:
        return current.date() - timedelta(days=1)
    return current.date()


def business_day_range(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(hour=BUSINESS_DAY_START_HOUR))
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start, end
```

- [ ] **Step 3: Rewrite task service**

`src/services/task_service.py` should expose:

- `create_task(data: TaskCreate) -> Task`
- `get_task(task_id: str) -> Task | None`
- `list_tasks(status: str | None = None, start: datetime | None = None, end: datetime | None = None, include_recurring: bool = True) -> list[Task]`
- `update_task(task_id: str, data: TaskUpdate) -> Task | None`
- `complete_task(task_id: str, data: TaskComplete) -> Task | None`
- `delete_task(task_id: str) -> bool`
- `archive_before(cutoff: datetime) -> int`

Completion only marks the task completed and sets `completed_at`; archival moves to `history_store` later at 02:00.

- [ ] **Step 4: Add service tests for completion and archival**

Tests must confirm:

- completion leaves the task in `tasks.json`
- `archive_before()` moves eligible tasks to `history.json`
- future tasks remain in `tasks.json`

---

## Task 3: Simplify Recurrence Rules

**Files:**
- Modify `src/models/recurrence.py`
- Modify `src/scheduler/recurrence_gen.py`
- Test `tests/test_scheduler.py`

- [ ] **Step 1: Rewrite recurrence model**

Use `RecurrenceTemplate` with only:

```python
class RecurrenceTemplate(BaseModel):
    title: str = Field(max_length=10)
    difficulty: int = Field(default=1, ge=0, le=3)
    time_mode: TimeMode = TimeMode.FLEXIBLE
    detail: str = ""
```

`Recurrence` keeps `id`, `title`, `enabled`, `pattern`, `interval_days`, `week_days`, `month_day`, `time_of_day`, `start_date`, `end_date`, `template`, `last_generated_for`.

- [ ] **Step 2: Generate task instances from rules**

`generate_recurring_tasks()` should:

- use `business_date()` as the target day
- skip disabled/out-of-range/already-generated rules
- create `TaskCreate` with `scheduled_at = target_day + time_of_day`
- set `recurrence_id = rec.id`
- set `last_generated_for = target_day`

- [ ] **Step 3: Update recurrence tests**

Tests should keep daily/weekly/monthly/interval generation checks, but assert `last_generated_for` and generated `Task.recurrence_id`.

---

## Task 4: Rebuild Tools for the New Schema

**Files:**
- Modify `src/tools/todo_tools.py`
- Test `tests/test_todo_tools.py`

- [ ] **Step 1: Replace tool surface**

Keep these tools only:

- `create_task`
- `get_task`
- `list_tasks`
- `update_task`
- `complete_task`
- `delete_task`
- `search_tasks`
- `create_recurrence`
- `list_recurrences`
- `disable_recurrence`

Remove `change_task_status` and old filter arguments.

- [ ] **Step 2: Tool schemas**

`create_task` schema must contain:

```json
{
  "title": "string max 10 chars",
  "difficulty": "integer 0..3",
  "time_mode": "flexible|time_critical",
  "scheduled_at": "ISO datetime",
  "detail": "markdown text"
}
```

`complete_task` schema must contain:

```json
{
  "task_id": "string",
  "completion_summary": "markdown text"
}
```

- [ ] **Step 3: Add tool tests**

Tests should assert:

- `urgency`, `category`, `tags`, `deadline`, `subtasks`, `notes`, `depends_on` are absent from tool schemas
- `create_task` accepts a future `scheduled_at`
- `complete_task` sets `status=completed` and keeps task active until archive

---

## Task 5: Rebuild Context Rendering and Prompt Rules

**Files:**
- Modify `src/context.py`
- Modify `prompts/system_prompt.md`
- Test `tests/test_prompt_context.py`

- [ ] **Step 1: Update context sections**

`build_runtime_context()` should produce:

- `current_time`
- `business_today`
- `today_tasks`
- `future_tasks`
- `recurring_tasks`

`today_tasks` includes current business-day tasks. `future_tasks` includes all non-recurring future tasks after the current business day. `recurring_tasks` lists recurrence rules once.

- [ ] **Step 2: Update display formatting**

Task lines should look like:

```text
- ➖ 21:00 🟣🟣🟣 开会
- ✅ 10:30 🔴🔴 写总结
- ➖ 18:00 🔴 运动（周期）
```

Do not show `recurrence_id`.

- [ ] **Step 3: Update prompt**

`prompts/system_prompt.md` must define:

- title is generated by LLM, <= 10 Chinese chars
- explicit clock time generally means `time_critical`
- vague period means `flexible` and must become concrete `scheduled_at`
- flexible periods: morning `08:00-12:00`, afternoon `13:00-18:00`, evening `19:00-22:00`
- business day starts at 02:00
- query decision boundary:
  - today -> current business-day tasks
  - tomorrow -> tomorrow’s tasks
  - future N days -> that range
  - arrangements -> today + future + recurrence summary
  - recurring tasks -> recurrence rules only

---

## Task 6: Reminder State and Dynamic Reminder Scan

**Files:**
- Modify `src/config.py`
- Modify `src/scheduler/reminder_scan.py`
- Test `tests/test_scheduler.py`

- [ ] **Step 1: Add config constant**

Add:

```python
REMINDER_STATE_FILE = DATA_DIR / "reminder_state.json"
```

Initialize it to `{}` in `ensure_data_dirs()`.

- [ ] **Step 2: Rewrite reminder scan**

Reminder offsets:

- `flexible`: `[20, 10]`
- `time_critical`: `[10, 5, 2]`

Trigger if:

- task is incomplete
- task has `scheduled_at`
- `0 <= now - (scheduled_at - offset) <= 90 seconds`
- key is not already in `reminder_state.json`

Key format:

```text
{task.id}:{offset}
```

- [ ] **Step 3: Add persistence tests**

Tests should confirm a reminder does not fire twice after `scan_reminders()` runs twice.

---

## Task 7: Archive at the 02:00 Boundary

**Files:**
- Modify `src/scheduler/engine.py`
- Create or modify `src/scheduler/archive_tasks.py`
- Test `tests/test_scheduler.py`

- [ ] **Step 1: Add archive job**

At `02:00`, archive tasks whose `scheduled_at` is before the start of the new business day.

- [ ] **Step 2: Run recurrence generation after archival**

The job ordering should be:

1. archive previous business-day task instances
2. generate current business-day recurrence instances

- [ ] **Step 3: Test job behavior**

Unit tests should call the archive function directly and assert:

- completed and incomplete previous-day tasks move to history
- future tasks stay active
- generated recurring tasks land in active tasks

---

## Task 8: Simplify Notifications, Morning, Evening, and Stats

**Files:**
- Modify `src/agent.py`
- Modify `src/scheduler/morning_push.py`
- Modify `src/scheduler/evening_push.py`
- Modify or remove `src/scheduler/overdue_scan.py`
- Modify or remove `src/scheduler/stats_gen.py`
- Test `tests/test_scheduler.py`

- [ ] **Step 1: Remove old overdue/category/stats assumptions**

Delete references to:

- `category`
- `importance`
- `deadline`
- `is_overdue`
- `completion.actual_minutes`
- `completion.summary`
- `subtasks`

- [ ] **Step 2: Format notifications using new task display**

Reminder text should include:

```text
【任务提醒】
➖ 21:00 🟣🟣🟣 开会
```

Evening review should include current business-day tasks and statuses.

---

## Task 9: Full Regression and Manual Test Script

**Files:**
- Modify `README.md`
- Modify `README_EN.md`

- [ ] **Step 1: Run automated tests**

Run:

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 2: Manual Matrix smoke test**

Run:

```bash
make run
```

Send Matrix messages:

```text
今晚9点开会
明天上午写总结，难度2
每天晚上6点提醒我运动
今天还有哪些任务？
我有哪些安排？
完成开会，总结：讨论了重构计划
```

Expected:

- explicit time creates `time_critical`
- vague period creates `flexible` with concrete `scheduled_at`
- daily recurrence creates a recurrence rule
- today query uses context
- arrangement query can include today, future, and recurrence summary
- completion marks the task completed and keeps it active until archive

---

## Self-Review

- Spec coverage: simplified fields, no `urgency`, recurrence as separate rules, `recurrence_id` internal only, business-day 02:00 boundary, reminder state JSON, prompt decision boundaries, and future non-recurring tasks are all covered.
- Placeholder scan: no implementation step uses TBD/TODO placeholders.
- Type consistency: task field names are `time_mode`, `scheduled_at`, `completed_at`, `completion_summary`, and `recurrence_id` throughout the plan.
