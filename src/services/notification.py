"""In-process notification channel from scheduler jobs to Agent."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class NotificationSink:
    _items: deque[dict[str, Any]] = field(default_factory=deque)
    _lock: Lock = field(default_factory=Lock)

    def publish(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(payload)

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._items)
            self._items.clear()
            return items


_SINK = NotificationSink()


def get_notification_sink() -> NotificationSink:
    return _SINK


def publish_notification(payload: dict[str, Any]) -> None:
    _SINK.publish(payload)
