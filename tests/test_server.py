import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen
import unittest

from sfc.server import SfcRequestHandler
from http.server import ThreadingHTTPServer
from sfc.events import Event, EventLog


ROOT = Path(__file__).parents[1]


class ServerTests(unittest.TestCase):
    def test_read_only_api_serves_health_and_world(self) -> None:
        handler = type("TestSfcHandler", (SfcRequestHandler,), {"world_path": ROOT / "examples/electrical-panel-clearance/project-world.json", "run_path": None})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/health") as response:
                self.assertEqual(json.loads(response.read())["status"], "ok")
            with urlopen(base + "/elements?q=LP-18") as response:
                self.assertEqual(len(json.loads(response.read())), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_project_deep_link_and_activity_projection(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            world_path = root / "world.json"
            world_path.write_text(json.dumps({"projectId": "P1", "elements": [{"elementId": "E1", "kind": "panel", "properties": {}}]}), encoding="utf-8")
            event_path = root / "events.jsonl"
            EventLog(event_path).append(Event("obligation.discovered", "OBL-1", {"status": "discovered"}))
            handler = type("DeepLinkSfcHandler", (SfcRequestHandler,), {"world_path": world_path, "run_path": None, "event_path": event_path})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/projects/P1/elements/E1") as response:
                    payload = json.loads(response.read())
                    self.assertEqual(payload["deepLink"], "/projects/P1/elements/E1")
                    self.assertEqual(payload["item"]["elementId"], "E1")
                with urlopen(base + "/tasks") as response:
                    self.assertEqual(json.loads(response.read())[0]["kind"], "obligation_classification")
            finally:
                server.shutdown()
                server.server_close()
