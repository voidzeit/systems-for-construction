"""Local read-only HTTP surface for Project World and canonical runs."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json

from .io import load_world, read_json


class SfcRequestHandler(BaseHTTPRequestHandler):
    world_path: Path | None = None
    run_path: Path | None = None

    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                studio = Path("apps/studio/index.html")
                if studio.exists():
                    self._send_html(200, studio.read_text(encoding="utf-8"))
                else:
                    self._send(404, {"error": "studio file not found"})
            elif parsed.path == "/health":
                self._send(200, {"status": "ok"})
            elif parsed.path == "/project":
                world = load_world(self.world_path) if self.world_path else None
                self._send(200, world.to_dict() if world else {"projectId": None, "elements": []})
            elif parsed.path == "/elements":
                world = load_world(self.world_path) if self.world_path else None
                query = parse_qs(parsed.query).get("q", [""])[0].lower()
                values = [item.to_dict() for item in (world.elements if world else ()) if not query or query in json.dumps(item.to_dict(), ensure_ascii=False).lower()]
                self._send(200, values)
            elif parsed.path == "/run":
                self._send(200, read_json(self.run_path) if self.run_path else {"run": None})
            else:
                self._send(404, {"error": "not found"})
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            self._send(400, {"error": str(error)})

    def log_message(self, format: str, *args) -> None:
        return


def serve(world_path: str | Path | None = None, run_path: str | Path | None = None, host: str = "127.0.0.1", port: int = 8787) -> None:
    handler = type("ConfiguredSfcHandler", (SfcRequestHandler,), {"world_path": Path(world_path) if world_path else None, "run_path": Path(run_path) if run_path else None})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"SFC server listening on http://{host}:{port}")
    server.serve_forever()
