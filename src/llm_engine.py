"""OpenAI-compatible LLM engine with tool-call loop."""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from time import perf_counter
from typing import Any

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - optional dependency in environments without LLM SDK
    AsyncOpenAI = None

from src.tool_registry import ToolRegistry
from src.markdown_media import extract_embedded_media_references

logger = logging.getLogger(__name__)

MAX_TOOL_CALL_ROUNDS = 10
_IMAGE_TAG_PATTERN = re.compile(r"\[image:(.+?):(.+?)\]")
_MUTATING_TOOLS = {
    "create_task",
    "update_task",
    "delete_task",
    "create_recurrence",
    "update_recurrence",
}
_DETAIL_MEDIA_TOOLS = {"create_task", "update_task"}


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


class LLMEngine:
    def __init__(
        self,
        client: Any | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "",
        system_prompt: str = "",
        tool_registry: ToolRegistry | None = None,
        context_hook: dict[str, str] | None = None,
        max_history: int = 20,
        temperature: float = 0.7,
        vision_enabled: bool = False,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            if AsyncOpenAI is None:
                raise RuntimeError(
                    "openai dependency is not installed; install requirements or pass client explicitly."
                )
            self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._system_prompt = system_prompt
        self._tool_registry = tool_registry or ToolRegistry()
        self._context_hook = context_hook or {}
        self._max_history = max_history
        self._temperature = temperature
        self._vision_enabled = vision_enabled
        self._histories: dict[str, list[dict[str, Any]]] = {}
        self._pending_media_references: dict[str, list[str]] = {}

    def _history(self, room_id: str) -> list[dict[str, Any]]:
        if room_id not in self._histories:
            self._histories[room_id] = []
        return self._histories[room_id]

    def _trim_history(self, room_id: str) -> None:
        history = self._history(room_id)
        max_len = self._max_history * 2
        if len(history) > max_len:
            self._histories[room_id] = history[-max_len:]

    @property
    def vision_enabled(self) -> bool:
        return self._vision_enabled

    def _build_messages(self, room_id: str, system_prompt: str | None = None) -> list[dict[str, Any]]:
        messages = [{"role": "system", "content": system_prompt or self._system_prompt}]
        messages.extend(self._history(room_id))
        if self._context_hook:
            messages.append({
                "role": "system",
                "content": json.dumps(self._context_hook, ensure_ascii=False),
            })
        return messages

    def _build_user_content(self, user_message: str) -> str | list[dict[str, Any]]:
        matches = _IMAGE_TAG_PATTERN.findall(user_message)
        if not matches or not self._vision_enabled:
            if matches:
                for file_path, mime_type in matches:
                    user_message = user_message.replace(
                        f"[image:{file_path}:{mime_type}]",
                        f"[image:{Path(file_path).name}]",
                    )
            return user_message

        content_parts: list[dict[str, Any]] = []
        text = _IMAGE_TAG_PATTERN.sub("", user_message).strip()
        if not text:
            text = "请分析以下媒体内容并给出处理建议"
        for file_path, mime_type in matches:
            try:
                data = Path(file_path).read_bytes()
            except OSError:
                continue
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64.b64encode(data).decode('utf-8')}",
                    },
                },
            )
        content_parts.append({"type": "text", "text": text})
        return content_parts

    async def chat(
        self,
        room_id: str,
        user_message: str,
        context_hook: dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        history = self._history(room_id)
        messages = self._build_messages(room_id, system_prompt=system_prompt)
        if context_hook:
            messages.append(
                {"role": "system", "content": json.dumps(context_hook, ensure_ascii=False)},
            )
        user_content = self._build_user_content(user_message)
        current_media_references = extract_embedded_media_references(user_message)
        if current_media_references:
            self._pending_media_references[room_id] = self._dedupe_media_references(
                [
                    *self._pending_media_references.get(room_id, []),
                    *current_media_references,
                ]
            )
        media_references = self._pending_media_references.get(room_id, [])
        messages.append({"role": "user", "content": user_content})
        history.append({"role": "user", "content": user_content})
        executed_mutations: dict[str, Any] = {}

        total_start = perf_counter()
        for round_index in range(1, MAX_TOOL_CALL_ROUNDS + 1):
            payload: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "temperature": self._temperature,
            }
            tools = self._tool_registry.definitions()
            if tools:
                payload["tools"] = tools

            request_start = perf_counter()
            completion = await self._create_completion(payload)
            logger.info(
                "perf llm_completion room=%s round=%s elapsed_ms=%s messages=%s tools=%s",
                room_id,
                round_index,
                _elapsed_ms(request_start),
                len(messages),
                len(tools),
            )
            message = completion.choices[0].message

            if not getattr(message, "tool_calls", None):
                content = message.content or ""
                history.append({"role": "assistant", "content": content})
                messages.append({"role": "assistant", "content": content})
                self._trim_history(room_id)
                logger.info(
                    "perf llm_chat_total room=%s rounds=%s elapsed_ms=%s reply_chars=%s",
                    room_id,
                    round_index,
                    _elapsed_ms(total_start),
                    len(content),
                )
                return content

            tool_calls = getattr(message, "tool_calls", [])
            logger.info(
                "perf llm_tool_calls room=%s round=%s count=%s names=%s",
                room_id,
                round_index,
                len(tool_calls),
                ",".join(tc.function.name for tc in tool_calls),
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            direct_replies: list[str] = []
            consumed_pending_media = False
            for tool_call in tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    result = {"error": "tool arguments decode error"}
                else:
                    try:
                        self._merge_media_references_into_args(
                            tool_call.function.name,
                            args,
                            media_references,
                        )
                        mutation_key = self._mutation_key(tool_call.function.name, args)
                        if mutation_key and mutation_key in executed_mutations:
                            tool_start = perf_counter()
                            result = {
                                "duplicate_tool_call_ignored": True,
                                "tool": tool_call.function.name,
                                "original_result": executed_mutations[mutation_key],
                            }
                            logger.info(
                                "perf tool_execute room=%s tool=%s duplicate=true elapsed_ms=%s",
                                room_id,
                                tool_call.function.name,
                                _elapsed_ms(tool_start),
                            )
                        else:
                            tool_start = perf_counter()
                            result = await self._tool_registry.execute_tool(
                                tool_call.function.name,
                                args,
                            )
                            logger.info(
                                "perf tool_execute room=%s tool=%s duplicate=false elapsed_ms=%s",
                                room_id,
                                tool_call.function.name,
                                _elapsed_ms(tool_start),
                            )
                            if mutation_key:
                                executed_mutations[mutation_key] = result
                            if (
                                tool_call.function.name in _DETAIL_MEDIA_TOOLS
                                and media_references
                                and not (
                                    isinstance(result, dict)
                                    and result.get("error")
                                )
                            ):
                                consumed_pending_media = True
                    except Exception as exc:
                        logger.exception("Tool execution failed: %s", tool_call.function.name)
                        result = {
                            "error": "tool execution failed",
                            "tool": tool_call.function.name,
                            "message": str(exc),
                        }
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
                history.append(
                    {
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
                direct_reply = self._direct_reply_from_tool_result(result)
                if direct_reply is not None:
                    direct_replies.append(direct_reply)
            if consumed_pending_media:
                self._pending_media_references.pop(room_id, None)
            if direct_replies:
                direct_reply = "\n\n".join(direct_replies)
                history.append({"role": "assistant", "content": direct_reply})
                self._trim_history(room_id)
                logger.info(
                    "perf llm_chat_total room=%s rounds=%s elapsed_ms=%s direct_tool_reply=true reply_chars=%s",
                    room_id,
                    round_index,
                    _elapsed_ms(total_start),
                    len(direct_reply),
                )
                return direct_reply

        fallback = "本轮对话工具链过长，请分步发起下一条需求。"
        history.append({"role": "assistant", "content": fallback})
        messages.append({"role": "assistant", "content": fallback})
        self._trim_history(room_id)
        logger.info(
            "perf llm_chat_total room=%s rounds=%s elapsed_ms=%s fallback=true",
            room_id,
            MAX_TOOL_CALL_ROUNDS,
            _elapsed_ms(total_start),
        )
        return fallback

    def _mutation_key(self, tool_name: str, args: dict[str, Any]) -> str | None:
        if tool_name not in _MUTATING_TOOLS:
            return None
        return json.dumps(
            {"tool": tool_name, "args": args},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    def _dedupe_media_references(self, media_references: list[str]) -> list[str]:
        deduped: list[str] = []
        for ref in media_references:
            if ref not in deduped:
                deduped.append(ref)
        return deduped

    def _direct_reply_from_tool_result(self, result: Any) -> str | None:
        if not isinstance(result, dict):
            return None
        if result.get("error"):
            return None
        message = result.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        task_table = result.get("task_markdown")
        if isinstance(task_table, str) and task_table.strip():
            return task_table.strip()
        table = result.get("current_business_day_tasks_markdown")
        if isinstance(table, str) and table.strip():
            return table.strip()
        return None

    def _merge_media_references_into_args(
        self,
        tool_name: str,
        args: dict[str, Any],
        media_references: list[str],
    ) -> None:
        if tool_name not in _DETAIL_MEDIA_TOOLS or not media_references:
            return
        current = str(args.get("detail") or "").strip()
        missing = [ref for ref in media_references if ref not in current]
        if not missing:
            return
        media_block = "\n".join(missing)
        args["detail"] = f"{media_block}\n{current}".strip() if current else media_block

    async def _create_completion(self, payload: dict[str, Any]) -> Any:
        if hasattr(self._client, "chat") and hasattr(self._client.chat, "completions"):
            return await self._client.chat.completions.create(**payload)
        if hasattr(self._client, "completions"):
            create = getattr(self._client.completions, "create")
            return await create(**payload)
        raise AttributeError("LLM client missing chat/completions endpoint")
