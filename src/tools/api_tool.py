"""REST API tool adapter."""

from __future__ import annotations

from inspect import isawaitable
from string import Formatter
from typing import Any

from src.tools.base import Tool, ToolDefinition


class APITool(Tool):
    def __init__(
        self,
        name: str,
        description: str,
        endpoint: str,
        method: str,
        parameters: dict[str, Any],
        headers: dict[str, str] | None = None,
        client: Any | None = None,
    ) -> None:
        self._name = name
        self._description = description
        self._endpoint = endpoint
        self._method = method.upper()
        self._parameters = parameters
        self._headers = headers or {}
        self._client = client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description=self._description,
            parameters={"type": "object", "properties": self._parameters, "required": []},
        )

    async def execute(self, arguments: dict[str, Any]) -> Any:
        path_params = {
            field for _, field, _, _ in Formatter().parse(self._endpoint) if field
        }

        endpoint = self._endpoint
        for key, value in arguments.items():
            endpoint = endpoint.replace("{" + key + "}", str(value))

        missing = {field for field in path_params if f"{{{field}}}" in endpoint}
        if missing:
            # At least one path placeholder was not supplied by arguments.
            raise ValueError(f"Missing path parameter(s): {', '.join(sorted(missing))}")

        request_kwargs: dict[str, Any] = {"headers": self._headers}
        if self._method == "GET":
            request_kwargs["params"] = {
                key: value for key, value in arguments.items() if f"{{{key}}}" not in self._endpoint
            }
        else:
            request_kwargs["json"] = {
                key: value for key, value in arguments.items() if f"{{{key}}}" not in self._endpoint
            }

        if self._client is None:
            import aiohttp

            async with aiohttp.ClientSession(headers=self._headers) as session:
                async with session.request(self._method, endpoint, **request_kwargs) as response:
                    return await self._decode_response(response)

        response = self._client.request(self._method, endpoint, **request_kwargs)
        if isawaitable(response):
            response = await response
        return await self._decode_response(response)

    async def _decode_response(self, response: Any) -> Any:
        if hasattr(response, "json"):
            try:
                json_attr = response.json
                json_result = json_attr() if callable(json_attr) else json_attr
            except Exception:
                json_result = None

            if json_result is not None:
                if isawaitable(json_result):
                    try:
                        return await json_result
                    except Exception:
                        # Some clients return non-JSON bodies; fall through to text.
                        pass
                return json_result

        if hasattr(response, "text"):
            try:
                text_attr = response.text
                text_result = text_attr() if callable(text_attr) else text_attr
            except Exception:
                text_result = None

            if text_result is not None:
                if isawaitable(text_result):
                    return await text_result
                return text_result

        return None
