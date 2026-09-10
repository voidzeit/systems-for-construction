"""Local read-only HTTP surface for Project World and canonical runs."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import os

from . import __version__
from .io import load_world, read_json
from .events import EventLog
from .activity import activity_feed, derive_tasks
from .readiness import compute_readiness
from .models import Determination, Evidence


#: Environment override for the Studio document.
STUDIO_VARIABLE = "SFC_STUDIO_PATH"

#: Repository checkout location, relative to this module rather than the
#: working directory, so serving does not depend on where the process started.
_REPOSITORY_STUDIO = Path(__file__).resolve().parents[4] / "apps" / "studio" / "index.html"


def studio_path(explicit: str | Path | None = None) -> Path | None:
    """Locate the Studio document, or None when this install does not carry one."""
    candidates = [explicit, os.environ.get(STUDIO_VARIABLE), _REPOSITORY_STUDIO]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


class SfcRequestHandler(BaseHTTPRequestHandler):
    world_path: Path | None = None
    run_path: Path | None = None
    evidence_path: Path | None = None
    event_path: Path | None = None
    studio: Path | None = None

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
                studio = self.studio or studio_path()
                if studio is not None:
                    self._send_html(200, studio.read_text(encoding="utf-8"))
                else:
                    self._send(404, {
                        "error": "studio document not found",
                        "hint": f"pass --studio, or set {STUDIO_VARIABLE}; the JSON endpoints are unaffected",
                        "endpoints": ["/health", "/project", "/elements", "/run", "/readiness", "/activity", "/tasks"],
                    })
            elif parsed.path == "/health":
                self._send(200, {"status": "ok", "version": __version__})
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
            elif parsed.path in {"/activity", "/tasks"}:
                events = EventLog(self.event_path).read() if self.event_path else []
                self._send(200, activity_feed(events) if parsed.path == "/activity" else [task.to_dict() for task in derive_tasks(events)])
            elif parsed.path == "/readiness":
                run = read_json(self.run_path) if self.run_path else {}
                run_document = run.get("run", run)
                source = read_json(self.evidence_path) if self.evidence_path else run.get("admittedEvidence", [])
                records = source if isinstance(source, list) else source.get("admitted", source.get("evidence", run.get("admittedEvidence", [source])))
                determinations = () if not run_document else (Determination.from_dict(run_document.get("determination", run_document)),)
                report = compute_readiness(determinations, tuple(Evidence.from_dict(item) for item in records))
                self._send(200, report.to_dict())
            elif parsed.path.startswith("/projects/"):
                self._send(200, self._deep_link(parsed.path))
            else:
                self._send(404, {"error": "not found"})
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            self._send(400, {"error": str(error)})

    def _deep_link(self, path: str) -> dict[str, object]:
        parts = path.strip("/").split("/")
        if len(parts) != 4 or parts[0] != "projects":
            raise ValueError("invalid project deep link")
        project_id, resource, resource_id = parts[1], parts[2], parts[3]
        world = load_world(self.world_path) if self.world_path else None
        if world and world.project_id != project_id:
            raise ValueError("project not found")
        item: object | None = None
        if resource == "elements" and world:
            item = next((element.to_dict() for element in world.elements if element.element_id == resource_id), None)
        elif resource == "runs" and self.run_path:
            candidate = read_json(self.run_path)
            item = candidate if candidate.get("runId") == resource_id else None
        elif resource == "evidence" and self.evidence_path:
            source = read_json(self.evidence_path)
            records = source if isinstance(source, list) else source.get("evidence", [source])
            item = next((record for record in records if record.get("evidenceId") == resource_id), None)
        elif resource == "requirements" and self.run_path:
            candidate = read_json(self.run_path)
            determination = candidate.get("determination", {})
            item = determination if determination.get("requirementId") == resource_id else None
        if item is None:
            raise ValueError(f"{resource[:-1] if resource.endswith('s') else resource} not found: {resource_id}")
        return {"projectId": project_id, "resource": resource[:-1] if resource.endswith("s") else resource, "id": resource_id, "deepLink": f"/projects/{project_id}/{resource}/{resource_id}", "item": item}

    def log_message(self, format: str, *args) -> None:
        return


def serve(world_path: str | Path | None = None, run_path: str | Path | None = None, host: str = "127.0.0.1", port: int = 8787, *, evidence_path: str | Path | None = None, event_path: str | Path | None = None, studio: str | Path | None = None) -> None:
    handler = type("ConfiguredSfcHandler", (SfcRequestHandler,), {"world_path": Path(world_path) if world_path else None, "run_path": Path(run_path) if run_path else None, "evidence_path": Path(evidence_path) if evidence_path else None, "event_path": Path(event_path) if event_path else None, "studio": studio_path(studio)})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"SFC server listening on http://{host}:{port}")
    server.serve_forever()
