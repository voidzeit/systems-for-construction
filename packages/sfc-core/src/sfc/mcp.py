"""Minimal JSON-RPC 2.0 MCP-style gateway with read-only resources.

This reference server intentionally has no mutation tool. Integrations may
wrap the same domain contracts with a full MCP SDK later.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .io import load_world, read_json


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
    {
        "name": "sfc.project.search",
        "description": "Search Project World elements by id, kind or property text.",
        "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "query": {"type": "string"}, "kind": {"type": "string"}}},
    },
    {
        "name": "sfc.element.get",
        "description": "Read one Project World element by id.",
        "inputSchema": {"type": "object", "required": ["path", "elementId"], "properties": {"path": {"type": "string"}, "elementId": {"type": "string"}}},
    },
    {
        "name": "sfc.relationships.query",
        "description": "Read relationships recorded in a Project World.",
        "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "elementId": {"type": "string"}}},
    },
    {
        "name": "sfc.evidence.get",
        "description": "Read an evidence document by id from a JSON ledger.",
        "inputSchema": {"type": "object", "required": ["path", "evidenceId"], "properties": {"path": {"type": "string"}, "evidenceId": {"type": "string"}}},
    },
    {
        "name": "sfc.requirement.get",
        "description": "Read a requirement or obligation contract.",
        "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
    },
    {
        "name": "sfc.run.inspect",
        "description": "Inspect a run and its determination.",
        "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
    },
    {
        "name": "sfc.geometry.measure",
        "description": "Read a deterministic geometry measurement already present on an element.",
        "inputSchema": {"type": "object", "required": ["path", "elementId", "property"], "properties": {"path": {"type": "string"}, "elementId": {"type": "string"}, "property": {"type": "string"}}},
    },
]


def _result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}]}


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    identifier = request.get("id")
    if method == "initialize":
        value = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "sfc-mcp", "version": __version__}, "capabilities": {"tools": {}}}
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
            if name in {"sfc.run.get", "sfc.run.inspect", "sfc.requirement.get"}:
                return {"jsonrpc": "2.0", "id": identifier, "result": _result(read_json(Path(arguments["path"])))}
            if name == "sfc.project.search":
                world = load_world(arguments["path"])
                query = str(arguments.get("query", "")).lower()
                kind = arguments.get("kind")
                matches = [element.to_dict() for element in world.elements if (not kind or element.kind == kind) and (not query or query in json.dumps(element.to_dict(), ensure_ascii=False).lower())]
                return {"jsonrpc": "2.0", "id": identifier, "result": _result(matches)}
            if name == "sfc.element.get":
                world = load_world(arguments["path"])
                element = next((item for item in world.elements if item.element_id == arguments["elementId"]), None)
                if element is None:
                    raise ValueError(f"element not found: {arguments['elementId']}")
                return {"jsonrpc": "2.0", "id": identifier, "result": _result(element.to_dict())}
            if name == "sfc.relationships.query":
                world = load_world(arguments["path"])
                element_id = arguments.get("elementId")
                relationships = [item for item in world.relationships if not element_id or element_id in item.values()]
                return {"jsonrpc": "2.0", "id": identifier, "result": _result(relationships)}
            if name == "sfc.evidence.get":
                ledger = read_json(Path(arguments["path"]))
                records = ledger if isinstance(ledger, list) else ledger.get("evidence", [ledger])
                record = next((item for item in records if item.get("evidenceId") == arguments["evidenceId"]), None)
                if record is None:
                    raise ValueError(f"evidence not found: {arguments['evidenceId']}")
                return {"jsonrpc": "2.0", "id": identifier, "result": _result(record)}
            if name == "sfc.geometry.measure":
                world = load_world(arguments["path"])
                element = next((item for item in world.elements if item.element_id == arguments["elementId"]), None)
                if element is None:
                    raise ValueError(f"element not found: {arguments['elementId']}")
                property_name = arguments["property"]
                values = element.properties if property_name in element.properties else element.geometry
                if property_name not in values:
                    raise ValueError(f"measurement not found: {property_name}")
                return {"jsonrpc": "2.0", "id": identifier, "result": _result({"elementId": element.element_id, "property": property_name, "value": values[property_name], "evidenceIds": list(element.evidence_by_property.get(property_name, ()))})}
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
