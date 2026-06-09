"""Thin Matrix client adapter used by the runtime agent."""
from __future__ import annotations

import asyncio
import inspect
import logging
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Awaitable, Callable, Optional

from nio import AsyncClient

from src.config import MatrixConfig

logger = logging.getLogger(__name__)


_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


@dataclass
class MatrixAttachment:
    url: str
    filename: str
    media_type: str
    mime_type: str | None = None


@dataclass
class MatrixEvent:
    """Normalized Matrix event payload."""

    room_id: str
    sender: str
    event_id: str | None
    msg_type: str
    content: str
    mxc_url: str | None = None
    media_path: Path | None = None
    media_mime: str | None = None
    media_filename: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def text_for_agent(self) -> str:
        if self.msg_type == "m.image" and self.media_path:
            return f"[image:{self.media_path}:{self.media_mime or 'image/*'}]"
        if self.msg_type == "m.image" and self.mxc_url and self.media_mime:
            return f"[image:{self.mxc_url}:{self.media_mime}]"
        if self.msg_type in {"m.video", "m.audio", "m.file"} and self.mxc_url:
            if self.media_mime:
                return f"{self.msg_type}:{self.mxc_url}:{self.media_mime}"
            return f"{self.msg_type}:{self.mxc_url}"
        return self.content


Callback = Callable[[str, MatrixEvent], Optional[Awaitable[None]]]
LegacyCallback = Callable[[str, str, str], Optional[Awaitable[None]]]
MatrixCallback = Callable[
    [str, str, str, list[MatrixAttachment]],
    Optional[Awaitable[None]],
]


class MatrixClient:
    """Small async Matrix client with text/media receive dispatch."""

    _TEXT_MSG_TYPES = {"m.text", "m.notice", "m.emote"}
    _MEDIA_MSG_TYPES = {"m.image", "m.video", "m.audio", "m.file"}

    def __init__(
        self,
        matrix_cfg: MatrixConfig,
        *,
        downloads_dir: Path | None = None,
        download_media: bool = True,
    ) -> None:
        self._matrix_cfg = matrix_cfg
        self._downloads_dir = downloads_dir or Path(".")
        self._downloads_dir.mkdir(parents=True, exist_ok=True)
        self._download_media = download_media
        self._client: AsyncClient | None = None
        self._sync_token: str | None = None
        self._callback: Callback | MatrixCallback | LegacyCallback | None = None
        self._running = False
        self._rooms = set(matrix_cfg.rooms)
        self._sync_task: asyncio.Task[None] | None = None
        self._seen_event_ids: set[str] = set()

    @property
    def rooms(self) -> list[str]:
        return sorted(self._rooms)

    def on_message(self, callback: MatrixCallback | LegacyCallback | Callback) -> None:
        self._callback = callback

    # keep backward compatibility with TodoAgent contract
    def set_message_handler(self, callback: MatrixCallback | LegacyCallback) -> None:
        self._callback = callback

    async def login(self) -> None:
        if self._client is None:
            self._client = AsyncClient(self._matrix_cfg.homeserver, self._matrix_cfg.user)
        if getattr(self._client, "logged_in", False):
            return
        try:
            response = await self._client.login(
                password=self._matrix_cfg.password,
                device_name="todo-agent",
            )
        except TypeError:
            # some matrix-nio versions accept positional login args
            response = await self._client.login(self._matrix_cfg.user, self._matrix_cfg.password)  # type: ignore[call-arg]
        if not getattr(response, "access_token", None):
            raise RuntimeError("Matrix 登录失败：未返回 access_token")
        await self._join_rooms()

    async def _join_rooms(self) -> None:
        if not self._rooms or self._client is None:
            return
        for room_id in sorted(self._rooms):
            try:
                await self._client.join(room_id)
            except Exception:
                # 已在房间内、房间不存在或权限不足时不打断启动
                logger.debug("join room ignored: %s", room_id, exc_info=True)

    async def start(self) -> None:
        await self.start_sync()

    async def stop(self) -> None:
        await self.logout()

    async def logout(self) -> None:
        self._running = False
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
        if self._client is None:
            return
        try:
            await self._client.logout()
        except Exception:
            pass
        await self._client.close()
        self._client = None

    async def send_text(
        self,
        room_id: str,
        text: str,
        content_extra: dict[str, Any] | None = None,
    ) -> None:
        if not text or self._client is None:
            return
        content = {"msgtype": "m.text", "body": text}
        if content_extra:
            content.update(content_extra)
        send_calls = [
            lambda: self._client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content,
            ),
            lambda: self._client.room_send(room_id, "m.room.message", content),
        ]
        for send in send_calls:
            try:
                start = perf_counter()
                await send()
                logger.info(
                    "perf matrix_room_send room=%s elapsed_ms=%s chars=%s",
                    room_id,
                    _elapsed_ms(start),
                    len(text),
                )
                return
            except TypeError:
                continue
            except Exception:
                logger.exception("发送消息失败（将尝试兼容签名重试）")
                continue

    async def set_typing(self, room_id: str, enabled: bool) -> None:
        if self._client is None or not self._matrix_cfg.typing_enabled:
            return
        timeout = self._matrix_cfg.typing_timeout_ms
        try:
            start = perf_counter()
            await self._client.room_typing(
                room_id=room_id,
                typing_state=enabled,
                timeout=timeout,
            )
            logger.info(
                "perf matrix_room_typing room=%s enabled=%s elapsed_ms=%s",
                room_id,
                enabled,
                _elapsed_ms(start),
            )
        except TypeError:
            try:
                start = perf_counter()
                await self._client.room_typing(room_id, enabled, timeout)
                logger.info(
                    "perf matrix_room_typing room=%s enabled=%s elapsed_ms=%s",
                    room_id,
                    enabled,
                    _elapsed_ms(start),
                )
            except TypeError:
                start = perf_counter()
                await self._client.room_typing(room_id, enabled)
                logger.info(
                    "perf matrix_room_typing room=%s enabled=%s elapsed_ms=%s",
                    room_id,
                    enabled,
                    _elapsed_ms(start),
                )

    async def download_media(
        self,
        mxc_url: str,
        filename: str,
        media_type: str = "file",
        mime_type: str | None = None,
    ) -> Path | None:
        return await self._download_mxc(
            room_id="",
            mxc_url=mxc_url,
            mime=mime_type,
            filename=filename,
            media_type=media_type,
        )

    async def start_sync(self) -> None:
        await self.login()
        if self._client is None:
            raise RuntimeError("Matrix client 未登录")
        self._running = True
        self._sync_task = asyncio.current_task()
        logger.info("Matrix sync started. rooms=%s", self.rooms)
        try:
            while self._running:
                try:
                    sync_start = perf_counter()
                    response = await self._client.sync(
                        timeout=30000,
                        since=self._sync_token,
                    )
                except TypeError:
                    sync_start = perf_counter()
                    response = await self._client.sync(30000, self._sync_token)
                logger.info("perf matrix_sync elapsed_ms=%s", _elapsed_ms(sync_start))
                is_initial_sync = self._sync_token is None
                self._sync_token = getattr(response, "next_batch", None)
                if is_initial_sync:
                    logger.info("Matrix initial sync completed; historical timeline skipped")
                    continue
                await self._process_rooms(response)
        except asyncio.CancelledError:
            return
        finally:
            self._running = False

    async def _process_rooms(self, sync_response: Any) -> None:
        rooms = getattr(sync_response, "rooms", None)
        if rooms is None:
            return
        joined = getattr(rooms, "join", {})
        for room_id, room_info in joined.items():
            if self._rooms and room_id not in self._rooms:
                continue
            timeline = getattr(room_info, "timeline", None)
            for event in getattr(timeline, "events", []) or []:
                parse_start = perf_counter()
                payload = await self._parse_event(room_id, event)
                logger.info(
                    "perf matrix_parse_event room=%s elapsed_ms=%s has_payload=%s",
                    room_id,
                    _elapsed_ms(parse_start),
                    payload is not None,
                )
                if payload is not None:
                    if payload.event_id and payload.event_id in self._seen_event_ids:
                        logger.debug("Skip duplicate Matrix event: %s", payload.event_id)
                        continue
                    if payload.event_id:
                        self._seen_event_ids.add(payload.event_id)
                    dispatch_start = perf_counter()
                    await self._dispatch(room_id, payload)
                    logger.info(
                        "perf matrix_dispatch room=%s event_id=%s elapsed_ms=%s",
                        room_id,
                        payload.event_id,
                        _elapsed_ms(dispatch_start),
                    )

    async def _dispatch(self, room_id: str, payload: MatrixEvent) -> None:
        if self._callback is None:
            return
        cb = self._callback
        params = 0
        try:
            params = len(
                [
                    p
                    for p in inspect.signature(cb).parameters.values()
                    if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                ]
            )
        except (TypeError, ValueError):
            pass

        if params >= 4:
            attachments = []
            if payload.msg_type in self._MEDIA_MSG_TYPES and payload.mxc_url:
                attachments = [
                    MatrixAttachment(
                        url=str(payload.mxc_url),
                        filename=payload.media_filename or "media",
                        media_type=payload.msg_type.removeprefix("m."),
                        mime_type=payload.media_mime,
                    ),
                ]
            result = cb(room_id, payload.sender, payload.text_for_agent, attachments)
        elif params >= 3:
            result = cb(room_id, payload.sender, payload.text_for_agent)
        else:
            result = cb(room_id, payload)
        if inspect.isawaitable(result):
            await result

    async def _parse_event(self, room_id: str, event: Any) -> MatrixEvent | None:
        source = self._event_source(event)
        if not source:
            return None

        if source.get("type") != "m.room.message":
            return None

        sender = source.get("sender", "")
        if sender == self._matrix_cfg.user:
            return None

        event_id = source.get("event_id")
        content = source.get("content", {}) or {}
        msg_type = str(content.get("msgtype", "m.text"))
        text = str(content.get("body", "") or "")

        event_payload = MatrixEvent(
            room_id=room_id,
            sender=sender,
            event_id=event_id,
            msg_type=msg_type,
            content=text,
            raw=source,
        )

        if msg_type in self._TEXT_MSG_TYPES:
            return event_payload

        if msg_type in self._MEDIA_MSG_TYPES:
            event_payload.mxc_url = content.get("url")
            info = content.get("info") if isinstance(content.get("info"), dict) else {}
            event_payload.media_mime = info.get("mimetype")
            raw_filename = str(content.get("body", "") or event_id or "media")
            event_payload.media_filename = self._safe_filename(raw_filename)
            media_type = msg_type.removeprefix("m.")
            if self._download_media:
                event_payload.media_path = await self._download_mxc(
                    mxc_url=event_payload.mxc_url,
                    mime=event_payload.media_mime,
                    filename=event_payload.media_filename,
                    media_type=media_type,
                )
            if event_payload.msg_type == "m.image" and event_payload.media_path is None and event_payload.media_mime:
                text = f"[image:{event_payload.mxc_url}:{event_payload.media_mime}]"
                event_payload.content = text
            return event_payload

        return None

    async def _download_mxc(
        self,
        mxc_url: str | None,
        mime: str | None,
        filename: str,
        media_type: str = "file",
    ) -> Path | None:
        if not mxc_url or not mxc_url.startswith("mxc://"):
            return None
        if self._client is None:
            return None

        token = self._client.access_token if getattr(self._client, "access_token", None) else None
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        _, _, media_id = mxc_url.partition("mxc://")
        if "/" not in media_id:
            return None
        server_name, _, media_key = media_id.partition("/")
        url = (
            f"{self._matrix_cfg.homeserver.rstrip('/')}/_matrix/media/v3/download/"
            f"{server_name}/{media_key}"
        )
        target = self._media_path(media_type, filename, mime)
        target.parent.mkdir(parents=True, exist_ok=True)

        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=120) as resp:
                    if resp.status != 200:
                        logger.warning("媒体下载失败: %s %s", mxc_url, resp.status)
                        return None
                    target.write_bytes(await resp.read())
            return target
        except Exception:
            logger.debug("可选 mxc 下载失败: %s", mxc_url, exc_info=True)
            return None

    def _media_path(self, media_type: str, filename: str, mime: str | None) -> Path:
        ext = Path(filename).suffix or self._guess_ext(mime)
        name = filename
        if ext and not name.endswith(ext):
            name = f"{name}{ext}"
        safe_name = self._safe_filename(name)
        category = self._category_for_mime(media_type, mime)
        return self._downloads_dir / category / safe_name

    def _category_for_mime(self, media_type: str | None, mime: str | None) -> str:
        media_type = (media_type or "").lower()
        if media_type == "image":
            return "imgs"
        if media_type == "video":
            return "videos"
        if media_type == "audio":
            return "audios"
        normalized = (mime or "").lower()
        if normalized.startswith("image/"):
            return "imgs"
        if normalized.startswith("video/"):
            return "videos"
        if normalized.startswith("audio/"):
            return "audios"
        return "files"

    def _safe_filename(self, raw: str) -> str:
        return _FILENAME_SAFE_RE.sub("_", raw).strip("_") or "media"

    def _guess_ext(self, mime: str | None) -> str:
        if not mime:
            return ".bin"
        ext = mimetypes.guess_extension(mime)
        return ext or ".bin"

    def _event_source(self, event: Any) -> dict[str, Any] | None:
        if isinstance(event, dict):
            return event
        source = getattr(event, "source", None)
        if isinstance(source, dict):
            return source
        if isinstance(event, object):
            data = dict(event.__dict__)
            if data:
                return data
        return None
