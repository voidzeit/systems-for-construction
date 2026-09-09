"""Minimal JSON-RPC 2.0 MCP-style gateway with read-only resources.

This reference server intentionally has no mutation tool. Integrations may
wrap the same domain contracts with a full MCP SDK later.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .io import read_json


TOOLS = [
    {
        "name": "sfc.project.inspect",
        "description": "Inspect a Project World summary.",
        "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
    },
    {
        "name": "sfc.run.get",
        "description": "Read a canonical or historical run JSON document.",
        "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
    },
]


def _result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}]}


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    identifier = request.get("id")
    if method == "initialize":
        value = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "sfc-mcp", "version": "0.1.0a1"}, "capabilities": {"tools": {}}}
        return {"jsonrpc": "2.0", "id": identifier, "result": value}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": identifier, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        try:
            if name == "sfc.project.inspect":
                document = read_json(Path(arguments["path"]))
                by_kind: dict[str, int] = {}
                for element in document.get("elements", []):
                    by_kind[element.get("kind", "unknown")] = by_kind.get(element.get("kind", "unknown"), 0) + 1
                return {"jsonrpc": "2.0", "id": identifier, "result": _result({"projectId": document.get("projectId"), "elements": len(document.get("elements", [])), "byKind": by_kind})}
            if name == "sfc.run.get":
                return {"jsonrpc": "2.0", "id": identifier, "result": _result(read_json(Path(arguments["path"])))}
            raise ValueError(f"unknown tool: {name}")
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
            return {"jsonrpc": "2.0", "id": identifier, "error": {"code": -32602, "message": str(error)}}
    if identifier is not None:
        return {"jsonrpc": "2.0", "id": identifier, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0

