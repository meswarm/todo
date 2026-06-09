import asyncio
from types import SimpleNamespace

from src.config import MatrixConfig
from src.matrix_client import MatrixClient


class FakeMatrixAPI:
    logged_in = True

    def __init__(self, responses):
        self._responses = list(responses)
        self.typing_calls = []
        self.sent = []

    async def sync(self, timeout=30000, since=None):
        if not self._responses:
            raise asyncio.CancelledError
        return self._responses.pop(0)

    async def logout(self):
        return None

    async def close(self):
        return None

    async def room_typing(self, room_id, typing_state, timeout=None):
        self.typing_calls.append((room_id, typing_state, timeout))
        return None

    async def room_send(self, room_id, message_type, content):
        self.sent.append((room_id, message_type, content))
        return None


def _sync_response(token: str, room_id: str, events: list[dict]):
    return SimpleNamespace(
        next_batch=token,
        rooms=SimpleNamespace(
            join={
                room_id: SimpleNamespace(
                    timeline=SimpleNamespace(events=events),
                )
            }
        ),
    )


def _message(event_id: str, body: str) -> dict:
    return {
        "type": "m.room.message",
        "sender": "@user:example",
        "event_id": event_id,
        "content": {"msgtype": "m.text", "body": body},
    }


def test_start_sync_skips_initial_historical_timeline(tmp_path):
    room_id = "!room:example"
    matrix = MatrixClient(
        MatrixConfig(
            homeserver="https://matrix.example",
            user="@bot:example",
            password="secret",
            rooms=[room_id],
        ),
        downloads_dir=tmp_path,
    )
    matrix._client = FakeMatrixAPI(
        [
            _sync_response("token_1", room_id, [_message("$old", "旧消息")]),
            _sync_response("token_2", room_id, [_message("$new", "新消息")]),
        ]
    )
    received = []

    async def on_message(room, sender, text, attachments):
        received.append((room, sender, text, attachments))
        matrix._running = False

    matrix.set_message_handler(on_message)

    asyncio.run(matrix.start_sync())

    assert [item[2] for item in received] == ["新消息"]


def test_send_text_can_add_notification_metadata(tmp_path):
    room_id = "!room:example"
    api = FakeMatrixAPI([])
    matrix = MatrixClient(
        MatrixConfig(
            homeserver="https://matrix.example",
            user="@bot:example",
            password="secret",
            rooms=[room_id],
        ),
        downloads_dir=tmp_path,
    )
    matrix._client = api

    asyncio.run(
        matrix.send_text(
            room_id,
            "## 提醒\n\n| ID | 标题 |",
            content_extra={"com.talk.kind": "notification"},
        )
    )

    assert api.sent == [
        (
            room_id,
            "m.room.message",
            {
                "msgtype": "m.text",
                "body": "## 提醒\n\n| ID | 标题 |",
                "com.talk.kind": "notification",
            },
        )
    ]


def test_start_sync_deduplicates_repeated_event_ids(tmp_path):
    room_id = "!room:example"
    matrix = MatrixClient(
        MatrixConfig(
            homeserver="https://matrix.example",
            user="@bot:example",
            password="secret",
            rooms=[room_id],
        ),
        downloads_dir=tmp_path,
    )
    matrix._client = FakeMatrixAPI(
        [
            _sync_response("token_1", room_id, []),
            _sync_response("token_2", room_id, [_message("$same", "创建任务")]),
            _sync_response("token_3", room_id, [_message("$same", "创建任务")]),
        ]
    )
    received = []

    async def on_message(room, sender, text, attachments):
        received.append((room, sender, text, attachments))

    matrix.set_message_handler(on_message)

    asyncio.run(matrix.start_sync())

    assert [item[2] for item in received] == ["创建任务"]


def test_set_typing_uses_configured_timeout(tmp_path):
    matrix = MatrixClient(
        MatrixConfig(
            homeserver="https://matrix.example",
            user="@bot:example",
            password="secret",
            rooms=["!room:example"],
            typing_timeout_ms=5000,
        ),
        downloads_dir=tmp_path,
    )
    api = FakeMatrixAPI([])
    matrix._client = api

    asyncio.run(matrix.set_typing("!room:example", True))

    assert api.typing_calls == [("!room:example", True, 5000)]


def test_set_typing_can_be_disabled(tmp_path):
    matrix = MatrixClient(
        MatrixConfig(
            homeserver="https://matrix.example",
            user="@bot:example",
            password="secret",
            rooms=["!room:example"],
            typing_enabled=False,
        ),
        downloads_dir=tmp_path,
    )
    api = FakeMatrixAPI([])
    matrix._client = api

    asyncio.run(matrix.set_typing("!room:example", True))

    assert api.typing_calls == []
