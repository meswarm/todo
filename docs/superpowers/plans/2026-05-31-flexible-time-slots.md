# Flexible Time Slots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add exact-time and flexible-slot task semantics, with slot labels in lists and grouped slot reminders.

**Architecture:** Keep `scheduled_at` as the internal datetime anchor, add `time_kind/time_slot` fields to the task model, and make formatters render slot tasks as `MM-DD 上午/下午/晚上`. Reminder scanning splits exact tasks into existing per-task reminders and slot tasks into grouped reminders at configured slot anchor times.

**Tech Stack:** Python 3.12, Pydantic models, APScheduler background jobs, JSON persistence, pytest.

---

### Task 1: Task Model and Slot Config

**Files:**
- Modify: `src/models/task.py`
- Modify: `src/models/__init__.py`
- Modify: `src/config.py`
- Modify: `.env.example`
- Test: `tests/test_models.py`
- Test: `tests/test_config.py`

- [ ] Add `TimeKind` and `TimeSlot` enums, default old tasks to exact, and validate slot consistency.
- [ ] Add `TODO_SLOT_MORNING_TIME`, `TODO_SLOT_AFTERNOON_TIME`, and `TODO_SLOT_EVENING_TIME` config parsing as `datetime.time`.
- [ ] Run `PYTHONPATH=. .venv/bin/python -m pytest tests/test_models.py tests/test_config.py -q`.

### Task 2: Display Formatting

**Files:**
- Modify: `src/context.py`
- Modify: `src/agent.py`
- Test: `tests/test_prompt_context.py`
- Test: `tests/test_agent_runtime.py`
- Test: `tests/test_todo_tools.py`

- [ ] Add a single formatter for task start labels: exact tasks use `MM-DD HH:MM`, slot tasks use `MM-DD 上午/下午/晚上`.
- [ ] Use it in task tables, notification tables, list shortcuts, and history output.
- [ ] Run `PYTHONPATH=. .venv/bin/python -m pytest tests/test_prompt_context.py tests/test_agent_runtime.py tests/test_todo_tools.py -q`.

### Task 3: Tool Schema and Prompt Rules

**Files:**
- Modify: `src/tools/todo_tools.py`
- Modify: `prompts/system_prompt.md`
- Test: `tests/test_todo_tools.py`

- [ ] Expose `time_kind` and `time_slot` in `create_task` and `update_task`.
- [ ] Keep exact recurring rules unchanged.
- [ ] Update prompt rules so vague date-only tasks ask for 上午/下午/晚上 instead of guessing a precise time.
- [ ] Run `PYTHONPATH=. .venv/bin/python -m pytest tests/test_todo_tools.py -q`.

### Task 4: Reminder Split

**Files:**
- Modify: `src/scheduler/reminder_scan.py`
- Modify: `src/agent.py`
- Test: `tests/test_scheduler.py`
- Test: `tests/test_agent_runtime.py`

- [ ] Make exact tasks keep `TODO_REMINDERS` per-task behavior.
- [ ] Make slot tasks skip per-task reminders.
- [ ] Add grouped slot reminder publishing with dedupe key `slot:<day>:<slot>:<HH:MM>`.
- [ ] Add Matrix formatting for grouped slot reminders as Markdown headings plus the standard task table.
- [ ] Run `PYTHONPATH=. .venv/bin/python -m pytest tests/test_scheduler.py tests/test_agent_runtime.py -q`.

### Task 5: Full Verification

**Files:**
- Modify as needed based on failing tests.

- [ ] Run `PYTHONPATH=. .venv/bin/python -m pytest tests/ -m 'not api' -q` with a temporary base dir if the real `.env` affects default-config tests.
- [ ] Run `make run`, verify startup logs, then stop the process with Ctrl-C.

