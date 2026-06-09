"""Todo-specific Matrix agent orchestration."""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from time import perf_counter
from datetime import date, datetime, timedelta
from typing import Any

from src.config import AppConfig
from src.context import _format_recurrences, _format_tasks, build_runtime_context, format_task_time_label, render_prompt_template
from src.markdown_media import parse_embedded_media
from src.llm_engine import LLMEngine
from src.matrix_client import MatrixAttachment, MatrixClient
from src.media_store import R2MediaStore
from src.models import Task
from src.services.notification import get_notification_sink
from src.services import task_service
from src.services.agenda_service import sort_tasks_for_agenda
from src.services.business_day import business_date
from src.skills import build_prompt_with_skills, load_skills_from_dir, load_system_prompt
from src.scheduler.recurrence_gen import skip_recurrence_occurrence
from src.tool_registry import ToolRegistry
import src.tools.todo_tools as todo_tools
from src.tools.todo_tools import build_todo_tools

logger = logging.getLogger(__name__)


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _is_allowed_media_room(room_id: str, allowed: set[str]) -> bool:
    if not allowed:
        return False
    if room_id in allowed:
        return True
    return room_id in {item.replace(" ", "") for item in allowed}


class TodoAgent:
    """Wire Matrix ingress with LLM and tool execution."""

    def __init__(
        self,
        config: AppConfig,
        matrix_client: MatrixClient,
        media_store: R2MediaStore,
        tool_registry: ToolRegistry | None = None,
        llm: LLMEngine | None = None,
    ) -> None:
        self._config = config
        self._matrix = matrix_client
        self._media_store = media_store
        self._matrix.set_message_handler(self.handle_matrix_message)

        self._tool_registry = tool_registry or ToolRegistry()
        self._register_tools()

        self._system_prompt_template = build_system_prompt(config)
        self._llm = llm or LLMEngine(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key,
            model=config.llm.model,
            system_prompt=self._system_prompt_template,
            tool_registry=self._tool_registry,
            max_history=config.llm.max_history,
            temperature=config.llm.temperature,
            vision_enabled=config.llm.vision_enabled,
        )

        self._rooms = set(config.matrix.rooms)
        self._stop_event = asyncio.Event()
        self._matrix_task: asyncio.Task[None] | None = None
        self._notification_task: asyncio.Task[None] | None = None
        self._running = False

    def _register_tools(self) -> None:
        for tool in build_todo_tools():
            try:
                self._tool_registry.register(tool)
            except ValueError:
                # idempotent registration during repeated startup paths.
                continue

    async def run(self) -> None:
        if self._running:
            return
        self._running = True
        self._matrix_task = asyncio.create_task(self._matrix.start())
        self._notification_task = asyncio.create_task(self._flush_notifications())
        stop_task = asyncio.create_task(self._stop_event.wait())
        try:
            done, _ = await asyncio.wait(
                {self._matrix_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self._matrix_task in done:
                self._matrix_task.result()
        finally:
            stop_task.cancel()
            await self.stop()

    async def stop(self) -> None:
        self._stop_event.set()
        if self._notification_task and not self._notification_task.done():
            self._notification_task.cancel()
            try:
                await self._notification_task
            except asyncio.CancelledError:
                pass
        if self._matrix_task and not self._matrix_task.done():
            self._matrix_task.cancel()
        await self._matrix.stop()
        self._running = False

    def request_stop(self) -> None:
        self._stop_event.set()

    async def handle_matrix_message(
        self,
        room_id: str,
        sender: str,
        text: str,
        attachments: list[MatrixAttachment],
    ) -> None:
        if not _is_allowed_media_room(room_id, self._rooms):
            logger.debug("Ignore message from unconfigured room: %s", room_id)
            return

        shortcut_reply = self._shortcut_list_reply(text, attachments)
        if shortcut_reply is not None:
            await self._matrix.send_text(room_id, shortcut_reply)
            return

        total_start = perf_counter()
        prompt = ""
        try:
            step_start = perf_counter()
            await self._matrix.set_typing(room_id, True)
            logger.info("perf matrix_typing_on room=%s elapsed_ms=%s", room_id, _elapsed_ms(step_start))

            step_start = perf_counter()
            prompt = await self._compose_prompt(text, attachments, room_id)
            logger.info(
                "perf compose_prompt room=%s elapsed_ms=%s prompt_chars=%s attachments=%s",
                room_id,
                _elapsed_ms(step_start),
                len(prompt),
                len(attachments),
            )

            step_start = perf_counter()
            runtime_context = build_runtime_context()
            context_values = runtime_context.as_mapping()
            logger.info("perf build_runtime_context room=%s elapsed_ms=%s", room_id, _elapsed_ms(step_start))

            step_start = perf_counter()
            system_prompt = render_prompt_template(
                self._system_prompt_template,
                context_values,
            )
            logger.info(
                "perf render_system_prompt room=%s elapsed_ms=%s prompt_chars=%s",
                room_id,
                _elapsed_ms(step_start),
                len(system_prompt),
            )

            step_start = perf_counter()
            reply = await self._llm.chat(room_id, prompt, system_prompt=system_prompt)
            logger.info(
                "perf llm_chat room=%s elapsed_ms=%s reply_chars=%s",
                room_id,
                _elapsed_ms(step_start),
                len(reply),
            )
        except Exception:
            logger.exception("Failed to handle Matrix message in room %s", room_id)
            reply = "我刚才处理这条消息时出错了。请再发一次，或补充更明确的日期、时间、任务对象。"
        finally:
            step_start = perf_counter()
            await self._matrix.set_typing(room_id, False)
            logger.info("perf matrix_typing_off room=%s elapsed_ms=%s", room_id, _elapsed_ms(step_start))
        step_start = perf_counter()
        await self._matrix.send_text(room_id, reply)
        logger.info(
            "perf matrix_send_text room=%s elapsed_ms=%s reply_chars=%s",
            room_id,
            _elapsed_ms(step_start),
            len(reply),
        )
        logger.info(
            "perf handle_matrix_message_total room=%s elapsed_ms=%s prompt_chars=%s reply_chars=%s",
            room_id,
            _elapsed_ms(total_start),
            len(prompt),
            len(reply),
        )

    async def _flush_notifications(self) -> None:
        sink = get_notification_sink()
        while not self._stop_event.is_set():
            payloads = sink.drain()
            if payloads:
                for payload in payloads:
                    message = self._format_notification(payload)
                    for room in self._rooms:
                        await self._matrix.send_text(
                            room,
                            message,
                            content_extra={"com.talk.kind": "notification"},
                        )
            await asyncio.sleep(2)

    async def _compose_prompt(
        self,
        text: str,
        attachments: list[MatrixAttachment],
        room_id: str,
    ) -> str:
        normalized = text or ""
        if not normalized and not attachments:
            return "用户发来非文本内容，请先给出简短处理说明。"
        if not normalized and attachments:
            return "当前只收到媒体消息，当前链路请直接发送包含 r2:// 的 Markdown 文本。"

        parts: list[str] = [normalized]

        embedded_media = parse_embedded_media(normalized) if normalized else []
        if embedded_media:
            logger.info("perf parse_embedded_media count=%s text_chars=%s", len(embedded_media), len(normalized))
        if embedded_media and any(
            [
                self._config.media.download_images,
                self._config.media.download_videos,
                self._config.media.download_audios,
                self._config.media.download_files,
            ]
        ):
            for item in embedded_media:
                if not self._can_download(item.kind):
                    continue
                download_start = perf_counter()
                if item.kind == "image" and self._llm._vision_enabled:
                    downloaded_path = await self._media_store.download_r2_uri(
                        item.url,
                        item.kind,
                    )
                    logger.info(
                        "perf r2_download kind=%s vision=true elapsed_ms=%s uri=%s",
                        item.kind,
                        _elapsed_ms(download_start),
                        item.url,
                    )
                    if downloaded_path:
                        mime_type, _ = mimetypes.guess_type(downloaded_path.name)
                        parts.append(
                            f"[image:{downloaded_path}:{mime_type or 'image/*'}]"
                        )
                else:
                    await self._media_store.download_r2_uri(item.url, item.kind)
                    logger.info(
                        "perf r2_download kind=%s vision=false elapsed_ms=%s uri=%s",
                        item.kind,
                        _elapsed_ms(download_start),
                        item.url,
                    )

        return "\n".join(part for part in parts if part).strip()

    def _shortcut_list_reply(
        self,
        text: str,
        attachments: list[MatrixAttachment],
    ) -> str | None:
        if attachments:
            return None

        command = (text or "").strip().lower()
        if command == "list today":
            return self._format_shortcut_task_section(
                "今日任务",
                self._agenda_tasks(todo_tools.business_date()),
            )
        if command == "list next":
            return self._format_next_tasks()
        history_reply = self._shortcut_history_reply(command)
        if history_reply is not None:
            return history_reply
        if command.startswith("delete "):
            target_id = command.removeprefix("delete ").strip()
            if not target_id or " " in target_id:
                return None
            return self._delete_by_shortcut(target_id)
        if command.startswith("complete "):
            target_id = command.removeprefix("complete ").strip()
            if not target_id or " " in target_id:
                return None
            return self._complete_by_shortcut(target_id)
        return None

    def _delete_by_shortcut(self, target_id: str) -> str:
        if target_id.startswith("rec_"):
            deleted = todo_tools.delete_recurrence(target_id)
            return (
                f"已删除周期任务规则 `{target_id}`"
                if deleted
                else f"未找到周期任务规则 `{target_id}`"
            )

        task = task_service.get_task(target_id)
        deleted = task_service.delete_task(target_id)
        if deleted and task and task.recurrence_id:
            skip_recurrence_occurrence(task.recurrence_id, business_date(task.scheduled_at))
        return (
            f"已删除任务 `{target_id}`"
            if deleted
            else f"未找到任务 `{target_id}`"
        )

    def _complete_by_shortcut(self, task_id: str) -> str:
        task = task_service.complete_task(task_id)
        status = (
            f"已完成任务 `{task_id}`"
            if task
            else f"未找到任务 `{task_id}`"
        )
        return "\n\n".join(
            [
                status,
                self._format_shortcut_task_section(
                    "今日任务",
                    self._agenda_tasks(todo_tools.business_date()),
                ),
            ]
        )

    def _format_next_tasks(self) -> str:
        today = todo_tools.business_date()
        tomorrow = today + timedelta(days=1)
        future_start = today + timedelta(days=2)
        future_tasks = sort_tasks_for_agenda(
            [
                task
                for task in task_service.task_store.load_all()
                if task.recurrence_id is None
                and business_date(task.scheduled_at) >= future_start
            ]
        )
        sections = [
            self._format_shortcut_task_section(
                "明日任务",
                self._agenda_tasks(tomorrow),
            ),
            self._format_shortcut_task_section("未来任务", future_tasks),
            "## 周期任务规则\n" + _format_recurrences(todo_tools.list_recurrences()),
        ]
        return "\n\n".join(sections)

    def _shortcut_history_reply(self, command: str) -> str | None:
        parts = command.split()
        if len(parts) != 3 or parts[:2] != ["list", "history"]:
            return None
        try:
            days = int(parts[2])
        except ValueError:
            return None
        if days <= 0:
            return None
        return self._format_history_tasks(days)

    def _format_history_tasks(self, days: int) -> str:
        today = todo_tools.business_date()
        history_tasks = task_service.history_store.load_all()
        sections: list[str] = []
        for offset in range(1, days + 1):
            day = today - timedelta(days=offset)
            tasks = sort_tasks_for_agenda(
                [
                    task
                    for task in history_tasks
                    if business_date(task.scheduled_at) == day
                ]
            )
            sections.append(
                self._format_shortcut_task_section(
                    f"历史任务 {day.isoformat()}",
                    tasks,
                )
            )
        return "\n\n".join(sections)

    def _agenda_tasks(self, day: date) -> list[Task]:
        payload = todo_tools.build_day_agenda(day)
        return [Task.model_validate(item) for item in payload["tasks"]]

    def _format_shortcut_task_section(self, title: str, tasks: list[Task]) -> str:
        return f"## {title}\n{_format_tasks(tasks)}"


    def _format_notification(self, payload: dict[str, Any]) -> str:
        p_type = payload.get("type", "notification")
        timestamp = payload.get("timestamp") or datetime.now().isoformat()
        data = payload.get("data", {})
        if p_type == "morning_agenda":
            today_tasks = data.get("today_tasks", [])
            return self._format_agenda_notification("今日任务", today_tasks)
        if p_type == "noon_agenda":
            today_tasks = data.get("today_tasks", [])
            return self._format_agenda_notification("今日任务", today_tasks)
        if p_type == "evening_agenda":
            tomorrow_tasks = data.get("tomorrow_tasks", [])
            return self._format_agenda_notification("明日任务", tomorrow_tasks)
        if p_type == "evening_review":
            today_tasks = data.get("today_tasks", [])
            lines = [
                "【晚间复盘】",
                f"业务日: {data.get('business_day', '')}",
                f"时间: {timestamp}",
                f"今日任务: {len(today_tasks)}",
            ]
            if today_tasks:
                lines.append("今日任务：")
                lines.append(self._format_notification_task_table(today_tasks[:8]))
            return "\n".join(lines)
        if p_type == "task_reminder":
            task = data.get("task", {})
            return self._format_task_reminder(task)
        if p_type == "slot_task_reminder":
            return self._format_slot_task_reminder(data)
        return f"{p_type}\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

    def _format_agenda_notification(self, title: str, tasks: Any) -> str:
        task_list = tasks if isinstance(tasks, list) else []
        body = self._format_notification_task_table(task_list[:8]) if task_list else "无"
        return f"## {title}\n{body}"

    def _format_task_reminder(self, task: dict[str, Any]) -> str:
        minutes_before = task.get("minutes_before", "?")
        return "\n".join(
            [
                f"## 🔔 提前 {minutes_before} 分钟提醒",
                "",
                self._format_notification_task_table([task]),
            ]
        )

    def _format_slot_task_reminder(self, data: dict[str, Any]) -> str:
        labels = {
            "morning": "上午",
            "afternoon": "下午",
            "evening": "晚上",
        }
        slot = str(data.get("time_slot", ""))
        title = f"## {labels.get(slot, slot or '时段')}任务提醒"
        tasks = data.get("tasks", [])
        return "\n\n".join(
            [
                title,
                self._format_notification_task_table(tasks if isinstance(tasks, list) else []),
            ]
        )

    def _format_notification_task_table(self, tasks: list[dict[str, Any]]) -> str:
        lines = [
            "| ID | 标题 | 开始时间 | 详情 |",
            "|---|---|---|---|",
        ]
        for task in tasks:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._notification_cell(task.get("id", "")),
                        self._notification_cell(task.get("title", "未命名")),
                        self._notification_task_time(task),
                        self._notification_cell(task.get("detail", "")),
                    ]
                )
                + " |"
            )
        return "\n".join(lines)

    def _notification_task_time(self, task: dict[str, Any]) -> str:
        value = task.get("scheduled_at")
        if task.get("completed"):
            return "✅"
        if not value:
            return ""
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
        return format_task_time_label(
            parsed,
            task.get("time_kind"),
            task.get("time_slot"),
        )

    def _notification_time(self, value: Any, *, time_only: bool = False) -> str:
        if not value:
            return "--:--" if time_only else ""
        text = str(value)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text[11:16] if time_only and len(text) >= 16 else text
        return parsed.strftime("%H:%M" if time_only else "%m-%d %H:%M")

    def _notification_cell(self, value: Any) -> str:
        return str(value or "").strip().replace("\n", "<br>").replace("|", "\\|")

    def _can_download(self, media_type: str) -> bool:
        config = self._config.media
        if media_type == "image":
            return config.download_images
        if media_type == "video":
            return config.download_videos
        if media_type == "audio":
            return config.download_audios
        return config.download_files

def build_system_prompt(config: AppConfig) -> str:
    prompt = load_system_prompt(config.prompt_path)
    if not config.skills_dir:
        return prompt
    skills = load_skills_from_dir(config.skills_dir)
    if not skills:
        return prompt
    return build_prompt_with_skills(prompt, skills)
