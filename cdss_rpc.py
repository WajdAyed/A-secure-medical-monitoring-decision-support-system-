"""Small MCP-style JSON-RPC 2.0 transport shared by CDSS services.

The clinical services intentionally expose only one HTTP endpoint (``POST /rpc``).
Business operations are advertised as MCP tools and invoked with ``tools/call``.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

import requests
from fastapi import Request
from fastapi.responses import JSONResponse, Response


JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-06-18"


@dataclass
class Tool:
    handler: Callable[..., Any]
    description: str
    input_schema: dict[str, Any]


class MCPJsonRpcServer:
    """JSON-RPC 2.0 dispatcher implementing the MCP tool discovery/call shape."""

    def __init__(self, name: str, version: str = "1.0.0") -> None:
        self.name = name
        self.version = version
        self._tools: dict[str, Tool] = {}

    def tool(self, name: str, description: str, input_schema: dict[str, Any]):
        def register(handler: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = Tool(handler, description, input_schema)
            return handler

        return register

    async def handle(self, request: Request) -> Response:
        try:
            message = await request.json()
        except Exception:
            return self._error(None, -32700, "Parse error")

        if not isinstance(message, dict) or message.get("jsonrpc") != JSONRPC_VERSION:
            return self._error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")

        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            return self._error(request_id, -32600, "Invalid Request")

        # Notifications (including MCP's notifications/initialized) have no id.
        if method == "notifications/initialized":
            return Response(status_code=202)

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                }
            elif method == "tools/list":
                result = {"tools": [
                    {"name": name, "description": tool.description, "inputSchema": tool.input_schema}
                    for name, tool in self._tools.items()
                ]}
            elif method == "tools/call":
                result = await self._call_tool(params)
            else:
                return self._error(request_id, -32601, "Method not found")
        except ValueError as exc:
            return self._error(request_id, -32602, "Invalid params", str(exc))
        except Exception as exc:  # Do not leak stack traces through the wire protocol.
            return self._error(request_id, -32603, "Internal error", str(exc))

        if "id" not in message:
            return Response(status_code=202)
        return JSONResponse({"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result})

    async def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or name not in self._tools:
            raise ValueError("Unknown tool")
        if not isinstance(arguments, dict):
            raise ValueError("tools/call arguments must be an object")

        tool = self._tools[name]
        result = tool.handler(**arguments)
        if inspect.isawaitable(result):
            result = await result
        # content preserves MCP interoperability; structuredContent makes service-to-service
        # calls lossless without requiring clients to parse a JSON text block.
        return {
            "content": [{"type": "text", "text": json.dumps(result, default=str)}],
            "structuredContent": result,
            "isError": isinstance(result, dict) and "error" in result,
        }

    @staticmethod
    def _error(request_id: Any, code: int, message: str, data: Any = None) -> JSONResponse:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return JSONResponse({"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error})


def call_tool(base_url: str, name: str, arguments: dict[str, Any] | None = None, timeout: float = 30) -> Any:
    """Call an MCP-style tool and return its structured JSON result."""
    response = requests.post(
        f"{base_url.rstrip('/')}/rpc",
        json={
            "jsonrpc": JSONRPC_VERSION,
            "id": str(uuid4()),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"JSON-RPC error: {payload['error']}")
    result = payload.get("result", {})
    if result.get("isError"):
        raise RuntimeError(f"Tool {name} failed: {result.get('structuredContent')}")
    return result.get("structuredContent")
