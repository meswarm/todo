"""Todo-specific Matrix agent orchestration."""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from time import perf_counter
from datetime import datetime
from typing import Any

from src.config import AppConfig
from src.context import build_runtime_context, render_prompt_template
from src.markdown_media import parse_embedded_media
from src.llm_engine import LLMEngine
from src.matrix_client import MatrixAttachment, MatrixClient
from src.media_store import R2MediaStore
from src.services.notification import get_notification_sink
from src.skills import build_prompt_with_skills, load_skills_from_dir, load_system_prompt
from src.tool_registry import ToolRegistry
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
                        await self._matrix.send_text(room, message)
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


    def _format_notification(self, payload: dict[str, Any]) -> str:
        p_type = payload.get("type", "notification")
        timestamp = payload.get("timestamp") or datetime.now().isoformat()
        data = payload.get("data", {})
        if p_type == "morning_agenda":
            today_tasks = data.get("today_tasks", [])
            future_tasks = data.get("future_tasks", [])
            lines = [
                "【早晨推送】",
                f"业务日: {data.get('business_day', '')}",
                f"时间: {timestamp}",
                f"今日任务: {len(today_tasks)}",
            ]
            if today_tasks:
                lines.append("今日任务：")
                lines.append(self._format_notification_task_table(today_tasks[:8]))
            if future_tasks:
                lines.append("未来任务：")
                lines.append(self._format_notification_task_table(future_tasks[:8]))
            return "\n".join(lines)
        if p_type == "evening_review":
            completed = data.get("completed_tasks", [])
            incomplete = data.get("incomplete_tasks", [])
            lines = [
                "【晚间复盘】",
                f"业务日: {data.get('business_day', '')}",
                f"时间: {timestamp}",
                f"完成: {len(completed)}",
                f"未完成: {len(incomplete)}",
            ]
            if completed:
                lines.append("已完成：")
                lines.append(self._format_notification_task_table(completed[:6]))
            if incomplete:
                lines.append("未完成：")
                lines.append(self._format_notification_task_table(incomplete[:6]))
            return "\n".join(lines)
        if p_type == "task_reminder":
            task = data.get("task", {})
            return self._format_task_reminder(task)
        return f"{p_type}\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

    def _format_task_reminder(self, task: dict[str, Any]) -> str:
        minutes_before = task.get("minutes_before", "?")
        return "\n".join(
            [
                f"🔔 提前 {minutes_before} 分钟提醒",
                "",
                self._format_notification_task_table([task]),
            ]
        )

    def _format_notification_task_table(self, tasks: list[dict[str, Any]]) -> str:
        lines = [
            "| ID | 标题 | 开始时间 | 详情 | 完成总结 |",
            "|---|---|---|---|---|",
        ]
        for task in tasks:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._notification_cell(task.get("id", "")),
                        self._notification_cell(task.get("title", "未命名")),
                        self._notification_time(task.get("scheduled_at")),
                        self._notification_cell(task.get("detail", "")),
                        self._notification_cell(task.get("completion_summary", "")),
                    ]
                )
                + " |"
            )
        return "\n".join(lines)

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
