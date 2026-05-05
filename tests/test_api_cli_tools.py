import pytest
import asyncio

from src.tools.api_tool import APITool
from src.tools.cli_tool import CLITool


def _run(coro):
    return asyncio.run(coro)


class FakeResponse:
    def __init__(self, payload, *, content_type: str = "application/json"):
        self._payload = payload
        self.headers = {"content-type": content_type}

    def json(self):
        return self._payload

    @property
    def text(self):
        return str(self._payload)


class AsyncJSONResponse:
    def __init__(self, payload, *, content_type: str = "application/json"):
        self._payload = payload
        self.headers = {"content-type": content_type}

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)


class FakeHTTPClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def test_api_tool_replaces_path_placeholders_and_queries():
    """Replace placeholders and keep remaining query params."""
    client = FakeHTTPClient(FakeResponse({"ok": True}))
    tool = APITool(
        name="get_item",
        description="Get item",
        endpoint="https://api.example/items/{item_id}",
        method="GET",
        parameters={"item_id": {"type": "string"}, "query": {"type": "string"}},
        client=client,
    )

    result = _run(tool.execute({"item_id": "abc", "query": "openai"}))

    assert result == {"ok": True}
    assert client.calls[0][1] == "https://api.example/items/abc"
    assert client.calls[0][2]["params"] == {"query": "openai"}


def test_api_tool_posts_non_get_payloads_as_json():
    client = FakeHTTPClient(FakeResponse({"ok": True}))
    tool = APITool(
        name="create_item",
        description="Create item",
        endpoint="https://api.example/items",
        method="POST",
        parameters={"title": {"type": "string"}, "body": {"type": "string"}},
        client=client,
    )

    result = _run(tool.execute({"title": "Task", "body": {"a": 1}}))

    assert result == {"ok": True}
    assert client.calls[0][2]["json"] == {"title": "Task", "body": {"a": 1}}


def test_api_tool_falls_back_to_text_from_awaitable_response():
    client = FakeHTTPClient(AsyncJSONResponse("done", content_type="text/plain"))
    tool = APITool(
        name="get_item",
        description="Get item",
        endpoint="https://api.example/items/{item_id}",
        method="GET",
        parameters={"item_id": {"type": "string"}},
        client=client,
    )

    result = _run(tool.execute({"item_id": "abc"}))

    assert result == "done"


def test_api_tool_missing_path_parameter():
    client = FakeHTTPClient(FakeResponse({"ok": True}))
    tool = APITool(
        name="get_item",
        description="Get item",
        endpoint="https://api.example/items/{item_id}",
        method="GET",
        parameters={"item_id": {"type": "string"}},
        client=client,
    )

    with pytest.raises(ValueError):
        _run(tool.execute({}))


def test_cli_tool_rejects_path_outside_work_dir(tmp_path):
    tool = CLITool(
        name="bad",
        description="Bad command",
        command="cat {path}",
        parameters={"path": {"type": "string"}},
        work_dir=tmp_path,
    )

    with pytest.raises(ValueError):
        _run(tool.execute({"path": "/etc/passwd"}))


def test_cli_tool_rejects_missing_placeholder(tmp_path):
    tool = CLITool(
        name="bad",
        description="Bad command",
        command="cat {path}",
        parameters={"path": {"type": "string"}},
        work_dir=tmp_path,
    )

    with pytest.raises(ValueError):
        _run(tool.execute({}))


def test_cli_tool_allows_path_inside_work_dir(tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello\n", encoding="utf-8")

    tool = CLITool(
        name="cat_ok",
        description="Read safe file",
        command="cat {path}",
        parameters={"path": {"type": "string"}},
        work_dir=tmp_path,
    )

    output = _run(tool.execute({"path": str(file_path)}))
    assert output["returncode"] == 0
    assert output["stdout"].strip() == "hello"


def test_cli_tool_rejects_relative_path_traversal(tmp_path):
    file_path = tmp_path.parent / "outside.txt"
    file_path.write_text("outside", encoding="utf-8")

    tool = CLITool(
        name="bad",
        description="Bad traversal",
        command="cat {path}",
        parameters={"path": {"type": "string"}},
        work_dir=tmp_path,
    )

    with pytest.raises(ValueError):
        _run(tool.execute({"path": "../outside.txt"}))
