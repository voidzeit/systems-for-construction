import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen
import unittest

from sfc.server import SfcRequestHandler
from http.server import ThreadingHTTPServer


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

