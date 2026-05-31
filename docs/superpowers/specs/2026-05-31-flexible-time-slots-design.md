# Flexible Time Slots Design

## Goal

The todo runtime should distinguish between two common task time styles:

1. Exact-time tasks, such as "今天下午 5 点打电话".
2. Flexible slot tasks, such as "今天下午买菜" or "明天晚上整理资料".

Exact-time tasks keep the current precise reminder behavior. Flexible slot tasks should not be forced into a fake precise time by the model, and they should be reminded once per slot as a group.

## Data Model

`Task` keeps `scheduled_at` as the internal datetime anchor and adds:

- `time_kind`: `"exact"` or `"slot"`.
- `time_slot`: `"morning"`, `"afternoon"`, `"evening"`, or `None`.

Rules:

- Existing tasks without these fields are treated as `time_kind="exact"` and `time_slot=None`.
- Exact tasks must have `time_kind="exact"` and no `time_slot`.
- Slot tasks must have `time_kind="slot"` and a valid `time_slot`.
- Slot tasks use `scheduled_at` as an internal anchor for filtering, sorting, archiving, and storage. The anchor is not presented to the user as an exact start time.

## Slot Configuration

Add environment settings:

```env
TODO_SLOT_MORNING_TIME=08:00
TODO_SLOT_AFTERNOON_TIME=14:00
TODO_SLOT_EVENING_TIME=18:00
```

These values define the internal anchor and group reminder time for each flexible slot. They must be parsed as `HH:MM`. Defaults are `08:00`, `14:00`, and `18:00`.

## Creation Flow

The LLM remains responsible for intent parsing and creation only when the user is creating or updating tasks.

Creation rules:

- If the user gives a concrete time point, create an exact task.
  - Example: "今天下午 5 点打电话" -> `time_kind="exact"`, `scheduled_at=17:00`.
- If the user gives a date and a broad slot, create a slot task.
  - Example: "今天下午买菜" -> `time_kind="slot"`, `time_slot="afternoon"`, `scheduled_at=<today 14:00 by config>`.
  - Example: "明天晚上整理资料" -> `time_kind="slot"`, `time_slot="evening"`, `scheduled_at=<tomorrow 18:00 by config>`.
- If the user gives a date but no time or slot, ask which slot: 上午、下午、晚上.
  - Example: "明天买菜" should not be converted to a guessed exact time.
- If the user gives neither date nor time information, ask for the missing date/time scope.

The `create_task` and `update_task` tools expose `time_kind` and `time_slot` so the LLM can write the time semantics explicitly.

## Display Rules

Task tables keep the current columns:

```md
| ID | 标题 | 开始时间 | 详情 |
|---|---|---|---|
```

The start-time cell is formatted by time semantics:

- Exact task: `MM-DD HH:MM`.
- Morning slot task: `MM-DD 上午`.
- Afternoon slot task: `MM-DD 下午`.
- Evening slot task: `MM-DD 晚上`.

This applies consistently to:

- Single task responses after create/update.
- `list today`.
- `list next`.
- `list history N`.
- Notifications and reminders.
- Runtime context shown to the LLM.

Sorting can continue to use `scheduled_at`, because the configured slot anchors provide stable order. With the default anchors, same-day order is morning slot, exact tasks by time, afternoon slot, exact tasks by time, evening slot, exact tasks by time.

## Reminder Rules

Exact-time tasks keep the existing per-task reminder logic:

- `TODO_REMINDERS=25,5` means each exact task is reminded 25 minutes and 5 minutes before `scheduled_at`.
- Existing dedupe by task id, reminder minutes, and scheduled time remains.

Slot tasks use grouped slot reminders:

- At the configured morning slot time, send one reminder containing all active morning slot tasks for the current business day.
- At the configured afternoon slot time, send one reminder containing all active afternoon slot tasks for the current business day.
- At the configured evening slot time, send one reminder containing all active evening slot tasks for the current business day.
- Slot tasks do not receive per-task `TODO_REMINDERS` reminders.

The grouped reminder title should be a Markdown heading, for example:

```md
## 上午任务提醒
```

The body uses the same task table formatter as other notifications.

Grouped reminders are deduped in `reminder_state.json` with a key containing the business day, slot, and configured anchor time, for example:

```text
slot:2026-05-31:afternoon:14:00
```

If a slot task is created after that slot's reminder time has already passed, the system does not send a catch-up reminder. The task remains visible in `list today`.

## Updates

Updating a task can change either exact time or slot semantics:

- Updating to a concrete time sets `time_kind="exact"` and clears `time_slot`.
- Updating to a broad slot sets `time_kind="slot"` and updates `time_slot` and `scheduled_at` to the configured anchor for that date.
- If the user only asks to change the title/detail, the existing time semantics stay unchanged.

After an update, the response remains a single task table for the updated task.

## Recurring Tasks

Initial implementation keeps recurring rules exact-time only. Recurrence still uses `time_of_day`, and generated task instances are `time_kind="exact"`.

Flexible recurring slots are intentionally out of scope for this phase. If needed later, recurrence can receive the same `time_kind/time_slot` fields.

## History and Archiving

Archiving continues to use `scheduled_at` and the business-day boundary. Since slot tasks use configured anchors on the intended date, they archive naturally with other tasks.

Historical display follows the same formatting rules as active lists:

- Exact historical task: `MM-DD HH:MM`.
- Slot historical task: `MM-DD 上午/下午/晚上`.

## Compatibility

No bulk migration is required.

Existing JSON tasks without `time_kind` and `time_slot` are loaded as exact tasks. Existing historical records may contain removed legacy fields such as `completed_at` or `completion_summary`; those remain ignored by the current model.

## Testing

Tests should cover:

- Model defaults for old tasks.
- Config parsing for slot anchor times.
- Create tool schema exposes `time_kind/time_slot`.
- Formatting exact tasks and slot tasks.
- `list today`, `list next`, and `list history N` display slot labels.
- Exact reminders still use `TODO_REMINDERS`.
- Slot reminders group tasks once per business day and do not use per-task reminders.
- Slot reminder dedupe keys include day, slot, and anchor time.
- Updating a task between exact and slot semantics.

