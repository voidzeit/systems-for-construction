import json
from pathlib import Path
from threading import Thread
import tempfile
from urllib.request import Request, urlopen
import unittest

from http.server import ThreadingHTTPServer

from sfc.gateway import GatewayPolicy, GatewayRoute, ProviderGateway, ProviderRegistry, ReferenceEmbeddingProvider, GatewayRequestHandler
from sfc.providers import ProviderRequest, ProviderResponse
from sfc.telemetry import UsageLedger


class FakeProvider:
    def __init__(self, text: str = "ok", fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.requests: list[ProviderRequest] = []

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("upstream unavailable")
        return ProviderResponse(self.text, request.model, request.model, 3, 2)


class GatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_quality_routing_and_fallback_are_recorded(self) -> None:
        registry = ProviderRegistry()
        failing = FakeProvider(fail=True)
        backup = FakeProvider("backup")
        registry.register_provider("primary", failing)
        registry.register_provider("backup", backup)
        registry.register_route(GatewayRoute("r-primary", "sfc/engineering-deep", "primary", "frontier", quality_score=.95))
        registry.register_route(GatewayRoute("r-backup", "sfc/engineering-deep", "backup", "local", quality_score=.8, local=True))
        ledger = UsageLedger(self.root / "usage.jsonl")
        gateway = ProviderGateway(registry, ledger=ledger)

        response = gateway.complete(logical_model="sfc/engineering-deep", prompt="inspect", metadata={"runId": "run-1"})

        self.assertEqual(response.text, "backup")
        self.assertEqual(backup.requests[0].model, "local")
        records = ledger.read()
        self.assertEqual(records[-1]["fallback"], True)
        self.assertEqual(records[-1]["runId"], "run-1")

    def test_openai_shaped_operations_and_local_embeddings(self) -> None:
        registry = ProviderRegistry()
        provider = FakeProvider("gateway response")
        registry.register_provider("reference", provider, embedding_provider=ReferenceEmbeddingProvider())
        registry.register_route(GatewayRoute("chat", "sfc/engineering-fast", "reference", "ref"))
        registry.register_route(GatewayRoute("private", "sfc/local-private", "reference", "ref", capabilities=("chat", "responses", "embeddings"), local=True))
        gateway = ProviderGateway(registry, ledger=UsageLedger(self.root / "operations.jsonl"))

        chat = gateway.chat_completion({"model": "sfc/engineering-fast", "messages": [{"role": "user", "content": "hello"}], "tools": [{"type": "function", "function": {"name": "inspect", "parameters": {"type": "object"}}}]})
        response = gateway.responses({"model": "sfc/engineering-fast", "input": "hello", "tools": [{"type": "function", "function": {"name": "inspect", "parameters": {"type": "object"}}}]})
        embeddings = gateway.embeddings({"model": "sfc/local-private", "input": ["hello", "world"]})

        self.assertEqual(chat["object"], "chat.completion")
        self.assertEqual(response["object"], "response")
        self.assertEqual(embeddings["data"][0]["object"], "embedding")
        self.assertEqual(len(embeddings["data"]), 2)
        self.assertEqual(provider.requests[0].tools[0]["name"], "inspect")
        self.assertEqual(provider.requests[1].tools[0]["name"], "inspect")

    def test_http_surface_lists_models_and_accepts_chat(self) -> None:
        registry = ProviderRegistry()
        registry.register_provider("reference", FakeProvider("hello"))
        registry.register_route(GatewayRoute("chat", "sfc/engineering-fast", "reference", "ref"))
        gateway = ProviderGateway(registry, ledger=UsageLedger(self.root / "http.jsonl"))
        handler = type("TestGatewayHandler", (GatewayRequestHandler,), {"gateway": gateway})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/v1/models") as result:
                self.assertEqual(json.loads(result.read())["data"][0]["id"], "sfc/engineering-fast")
            request = Request(base + "/v1/chat/completions", data=json.dumps({"model": "sfc/engineering-fast", "messages": [{"role": "user", "content": "hello"}]}).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request) as result:
                self.assertEqual(json.loads(result.read())["choices"][0]["message"]["content"], "hello")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
