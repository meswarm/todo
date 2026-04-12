"""JSON 文件存储层（带文件锁）"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar, Type

from filelock import FileLock
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class JsonStore:
    """通用 JSON 列表存储"""

    def __init__(self, file_path: Path, model_class: Type[T]):
        self.file_path = file_path
        self.model_class = model_class
        self.lock = FileLock(str(file_path) + ".lock")

    def _read_raw(self) -> list[dict]:
        if not self.file_path.exists():
            return []
        text = self.file_path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        data = json.loads(text)
        return data if isinstance(data, list) else []

    def _write_raw(self, data: list[dict]):
        self.file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def load_all(self) -> list[T]:
        with self.lock:
            return [self.model_class.model_validate(item) for item in self._read_raw()]

    def save_all(self, items: list[T]):
        with self.lock:
            self._write_raw([item.model_dump(mode="json") for item in items])

    def find_by_id(self, item_id: str) -> T | None:
        for item in self.load_all():
            if getattr(item, "id", None) == item_id:
                return item
        return None

    def add(self, item: T):
        with self.lock:
            data = self._read_raw()
            data.append(item.model_dump(mode="json"))
            self._write_raw(data)

    def update(self, item_id: str, updated: T) -> bool:
        with self.lock:
            data = self._read_raw()
            for i, d in enumerate(data):
                if d.get("id") == item_id:
                    data[i] = updated.model_dump(mode="json")
                    self._write_raw(data)
                    return True
            return False

    def delete(self, item_id: str) -> bool:
        with self.lock:
            data = self._read_raw()
            new_data = [d for d in data if d.get("id") != item_id]
            if len(new_data) == len(data):
                return False
            self._write_raw(new_data)
            return True

    def move_to(self, item_id: str, target_store: "JsonStore") -> bool:
        """将 item 从当前 store 移动到 target_store"""
        with self.lock:
            data = self._read_raw()
            item_data = None
            new_data = []
            for d in data:
                if d.get("id") == item_id:
                    item_data = d
                else:
                    new_data.append(d)
            if item_data is None:
                return False
            self._write_raw(new_data)
        # 追加到目标 store
        with target_store.lock:
            target_data = target_store._read_raw()
            target_data.append(item_data)
            target_store._write_raw(target_data)
        return True
