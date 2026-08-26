#!/usr/bin/env python3
"""Streamable HTTP adapter exposing four vendor-separated MCP endpoints."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from salesbench.contracts import CONTRACT_PINS
    from salesbench.runtime.world import SalesWorld
except ImportError:  # Standalone Harbor world image.
    from contracts import CONTRACT_PINS  # type: ignore[no-redef]
    from world import SalesWorld  # type: ignore[no-redef]


WORLD = SalesWorld(
    Path(os.environ.get("SALESBENCH_DOCUMENTS", "/workspace/documents")),
    Path(os.environ.get("SALESBENCH_OUTPUT", "/workspace/output")),
    Path(os.environ.get("SALESBENCH_STATE", "/workspace/state")),
    Path(os.environ.get("SALESBENCH_SPEC", "/opt/salesbench/spec.json")),
    Path(os.environ.get("SALESBENCH_SEED", "/opt/salesbench/seed.json")),
)

SERVERS = ("filesystem", "salesforce", "hubspot", "gong")


def rpc_response(server: str, request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    if request_id is None and isinstance(method, str) and method.startswith("notifications/"):
        return None
    if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": CONTRACT_PINS["protocol_version"],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": f"salesbench-{server}", "version": "1.0.0"},
                "instructions": (
                    "Operate only on this isolated synthetic SalesBench task. "
                    "Gong is read-only and final files belong under /workspace/output."
                ),
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": WORLD.list_tools(server)},
        }
    if method == "tools/call":
        params = request.get("params")
        if not isinstance(params, dict):
            params = {}
        result = WORLD.call_tool(
            server,
            str(params.get("name", "")),
            params.get("arguments"),
        )
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": "Method not found"},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "SalesBenchMCP/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json(self, status: int, value: Any) -> None:
        payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("MCP-Protocol-Version", CONTRACT_PINS["protocol_version"])
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok", "task_id": WORLD.spec["task_id"]})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/verify":
            try:
                report = WORLD.verify(self.headers.get("X-Verify-Token"))
            except PermissionError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            self._json(HTTPStatus.OK, report)
            return
        server = self.path.removeprefix("/mcp/")
        if server not in SERVERS or self.path != f"/mcp/{server}":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            request = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            )
            return
        if isinstance(request, list):
            responses = [
                response
                for item in request
                if isinstance(item, dict)
                and (response := rpc_response(server, item)) is not None
            ]
            self._json(HTTPStatus.OK, responses)
            return
        if not isinstance(request, dict):
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}},
            )
            return
        response = rpc_response(server, request)
        if response is None:
            self.send_response(HTTPStatus.ACCEPTED)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._json(HTTPStatus.OK, response)


if __name__ == "__main__":
    host = os.environ.get("SALESBENCH_HOST", "0.0.0.0")
    port = int(os.environ.get("SALESBENCH_PORT", "8972"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()
