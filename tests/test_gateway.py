import json
import os
from pathlib import Path
from threading import Thread
from unittest import mock
import tempfile
from urllib.request import Request, urlopen
import unittest

from http.server import ThreadingHTTPServer

from sfc.gateway import (
    IN_PROCESS,
    DataResidency,
    ExecutionScope,
    GatewayError,
    GatewayPolicy,
    GatewayRequestHandler,
    GatewayRoute,
    ProviderGateway,
    ProviderRegistry,
    ReferenceEmbeddingProvider,
    build_default_gateway,
)
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
        registry.register_route(GatewayRoute("r-backup", "sfc/engineering-deep", "backup", "local", quality_score=.8, **IN_PROCESS))
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
        registry.register_route(GatewayRoute("private", "sfc/local-private", "reference", "ref", capabilities=("chat", "responses", "embeddings"), **IN_PROCESS))
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


class DeploymentSemanticsTests(unittest.TestCase):
    """A route is local because of what it is, not because of what it is called."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def _registry(self) -> ProviderRegistry:
        registry = ProviderRegistry()
        registry.register_provider("reference", FakeProvider("local"), embedding_provider=ReferenceEmbeddingProvider())
        registry.register_provider("vendor", FakeProvider("remote"))
        registry.register_provider("onprem", FakeProvider("onprem"))
        registry.register_route(GatewayRoute("r-local", "sfc/engineering-fast", "reference", "ref", quality_score=.7, **IN_PROCESS))
        registry.register_route(GatewayRoute("r-vendor", "sfc/engineering-fast", "vendor", "frontier", quality_score=.95))
        registry.register_route(GatewayRoute(
            "r-onprem", "sfc/engineering-fast", "onprem", "self-hosted", quality_score=.85,
            execution_scope=ExecutionScope.PRIVATE_CLOUD, data_residency=DataResidency.REGION, network_required=True,
        ))
        return registry

    def test_a_name_does_not_make_a_route_local(self) -> None:
        misnamed = GatewayRoute("route-local-private", "sfc/local-private", "vendor", "frontier")
        self.assertFalse(misnamed.is_local)
        self.assertFalse(misnamed.to_dict()["local"])

    def test_local_requires_scope_residency_and_no_network(self) -> None:
        self.assertTrue(GatewayRoute("r", "m", "p", "u", **IN_PROCESS).is_local)
        for override in (
            {"execution_scope": ExecutionScope.PRIVATE_CLOUD},
            {"data_residency": DataResidency.REGION},
            {"network_required": True},
        ):
            with self.subTest(override=override):
                properties = {**IN_PROCESS, **override}
                self.assertFalse(GatewayRoute("r", "m", "p", "u", **properties).is_local)

    def test_local_only_policy_selects_by_property(self) -> None:
        router = ProviderGateway(self._registry(), policy=GatewayPolicy(local_only=True)).router
        candidates = router.candidates("sfc/engineering-fast")
        self.assertEqual([route.route_id for route in candidates], ["r-local"])

    def test_a_local_only_policy_explains_the_refusal(self) -> None:
        policy = GatewayPolicy(local_only=True)
        with self.assertRaises(PermissionError) as raised:
            policy.authorize(GatewayRoute("r-vendor", "m", "vendor", "frontier"))
        self.assertIn("public_cloud", str(raised.exception))
        self.assertIn("external", str(raised.exception))

    def test_restricted_sensitivity_requires_local_execution(self) -> None:
        router = ProviderGateway(self._registry()).router
        routes = router.candidates("sfc/engineering-fast", metadata={"projectSensitivity": "restricted"})
        self.assertEqual([route.route_id for route in routes], ["r-local"])

    def test_confidential_sensitivity_admits_a_private_cloud(self) -> None:
        router = ProviderGateway(self._registry()).router
        routes = router.candidates("sfc/engineering-fast", metadata={"projectSensitivity": "confidential"})
        self.assertEqual(sorted(route.route_id for route in routes), ["r-local", "r-onprem"])

    def test_a_sensitivity_survives_surface_formatting(self) -> None:
        router = ProviderGateway(self._registry()).router
        for spelling in ("restricted", " Restricted ", "RESTRICTED"):
            with self.subTest(spelling=spelling):
                routes = router.candidates("sfc/engineering-fast", metadata={"projectSensitivity": spelling})
                self.assertEqual([route.route_id for route in routes], ["r-local"])

    def test_an_unknown_sensitivity_fails_closed(self) -> None:
        router = ProviderGateway(self._registry()).router
        with self.assertRaises(GatewayError) as raised:
            router.candidates("sfc/engineering-fast", metadata={"projectSensitivity": "top_secret"})
        self.assertIn("unknown project sensitivity", str(raised.exception))

    def test_no_constraint_must_be_stated_explicitly(self) -> None:
        router = ProviderGateway(self._registry()).router
        without = router.candidates("sfc/engineering-fast")
        unrestricted = router.candidates("sfc/engineering-fast", metadata={"projectSensitivity": "unrestricted"})
        self.assertEqual([route.route_id for route in without], [route.route_id for route in unrestricted])

    def test_required_execution_scope_is_enforced(self) -> None:
        policy = GatewayPolicy(required_execution_scopes=frozenset({ExecutionScope.LOCAL, ExecutionScope.PRIVATE_CLOUD}))
        router = ProviderGateway(self._registry(), policy=policy).router
        self.assertEqual(sorted(route.route_id for route in router.candidates("sfc/engineering-fast")), ["r-local", "r-onprem"])

    def test_maximum_data_residency_permits_everything_closer_to_the_device(self) -> None:
        policy = GatewayPolicy(maximum_data_residency=DataResidency.REGION)
        router = ProviderGateway(self._registry(), policy=policy).router
        self.assertEqual(sorted(route.route_id for route in router.candidates("sfc/engineering-fast")), ["r-local", "r-onprem"])

    def test_routes_publish_their_deployment_properties(self) -> None:
        document = GatewayRoute("r-onprem", "m", "onprem", "u", execution_scope=ExecutionScope.PRIVATE_CLOUD, data_residency=DataResidency.REGION).to_dict()
        self.assertEqual(document["executionScope"], "private_cloud")
        self.assertEqual(document["dataResidency"], "region")
        self.assertTrue(document["networkRequired"])
        self.assertFalse(document["local"])


class DefaultGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.ledger = self.root / "usage.jsonl"

    def _build(self, **environment: str) -> ProviderGateway:
        with mock.patch.dict(os.environ, environment, clear=False):
            for key in ("SFC_GATEWAY_PROVIDER", "SFC_GATEWAY_LOCAL_ONLY", "SFC_PROVIDER", "SFC_MODEL",
                        "SFC_GATEWAY_EXECUTION_SCOPE", "SFC_GATEWAY_DATA_RESIDENCY"):
                if key not in environment:
                    os.environ.pop(key, None)
            return build_default_gateway(ledger_path=self.ledger)

    def test_local_private_is_local_in_the_default_build(self) -> None:
        gateway = self._build()
        route = gateway.router.select("sfc/local-private")
        self.assertTrue(route.is_local)
        self.assertEqual(route.provider, "reference")

    def test_local_private_stays_local_when_an_upstream_is_configured(self) -> None:
        gateway = self._build(SFC_GATEWAY_PROVIDER="environment", SFC_PROVIDER="openai-compatible")
        route = gateway.router.select("sfc/local-private")
        self.assertTrue(route.is_local, "sfc/local-private must not be served by an upstream provider")
        self.assertEqual(route.provider, "reference")
        # The upstream route is registered, and honest about what it is.
        upstream = gateway.router.select("sfc/engineering-fast")
        self.assertFalse(upstream.is_local)
        self.assertIs(upstream.execution_scope, ExecutionScope.PUBLIC_CLOUD)

    def test_local_only_still_leaves_a_usable_route(self) -> None:
        gateway = self._build(SFC_GATEWAY_PROVIDER="environment", SFC_PROVIDER="openai-compatible", SFC_GATEWAY_LOCAL_ONLY="true")
        routes = [route for route in gateway.registry.routes if gateway.router._allowed(route)]
        self.assertTrue(routes, "a local-only policy must not empty the routing table")
        self.assertTrue(all(route.is_local for route in routes))
        self.assertEqual(gateway.router.select("sfc/local-private").route_id, "route-local-private")

    def test_local_only_refuses_a_model_that_has_no_local_route(self) -> None:
        gateway = self._build(SFC_GATEWAY_PROVIDER="environment", SFC_PROVIDER="openai-compatible", SFC_GATEWAY_LOCAL_ONLY="true")
        with self.assertRaises(GatewayError):
            gateway.complete(logical_model="sfc/engineering-deep", prompt="inspect")

    def test_a_self_hosted_upstream_can_declare_what_it_is(self) -> None:
        gateway = self._build(
            SFC_GATEWAY_PROVIDER="environment", SFC_PROVIDER="openai-compatible",
            SFC_GATEWAY_EXECUTION_SCOPE="private_cloud", SFC_GATEWAY_DATA_RESIDENCY="region",
        )
        route = gateway.router.select("sfc/engineering-deep")
        self.assertIs(route.execution_scope, ExecutionScope.PRIVATE_CLOUD)
        self.assertIs(route.data_residency, DataResidency.REGION)
        self.assertFalse(route.is_local, "a self-hosted deployment reached over the network is not on the device")


class ApiKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def _serve(self, policy: GatewayPolicy) -> tuple[ThreadingHTTPServer, str]:
        registry = ProviderRegistry()
        registry.register_provider("reference", FakeProvider("hello"))
        registry.register_route(GatewayRoute("chat", "sfc/engineering-fast", "reference", "ref", **IN_PROCESS))
        gateway = ProviderGateway(registry, policy=policy, ledger=UsageLedger(self.root / "auth.jsonl"))
        handler = type("AuthGatewayHandler", (GatewayRequestHandler,), {"gateway": gateway})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, f"http://127.0.0.1:{server.server_port}"

    def test_a_configured_key_is_required(self) -> None:
        from urllib.error import HTTPError

        _, base = self._serve(GatewayPolicy(api_key="secret"))
        with self.assertRaises(HTTPError) as raised:
            urlopen(Request(base + "/v1/models"))
        self.assertEqual(raised.exception.code, 401)

    def test_the_correct_key_is_accepted(self) -> None:
        _, base = self._serve(GatewayPolicy(api_key="secret"))
        request = Request(base + "/v1/models", headers={"Authorization": "Bearer secret"})
        with urlopen(request) as result:
            self.assertEqual(json.loads(result.read())["data"][0]["id"], "sfc/engineering-fast")

    def test_a_prefix_of_the_key_is_rejected(self) -> None:
        from urllib.error import HTTPError

        _, base = self._serve(GatewayPolicy(api_key="secret"))
        request = Request(base + "/v1/models", headers={"Authorization": "Bearer sec"})
        with self.assertRaises(HTTPError) as raised:
            urlopen(request)
        self.assertEqual(raised.exception.code, 401)

    def test_the_policy_is_inspectable_without_revealing_the_key(self) -> None:
        _, base = self._serve(GatewayPolicy(api_key="secret", local_only=True))
        request = Request(base + "/v1/policy", headers={"Authorization": "Bearer secret"})
        with urlopen(request) as result:
            payload = json.loads(result.read())
        self.assertTrue(payload["apiKeyRequired"])
        self.assertTrue(payload["localOnly"])
        self.assertNotIn("secret", json.dumps(payload))

    def test_routes_expose_their_deployment_properties_over_http(self) -> None:
        _, base = self._serve(GatewayPolicy())
        with urlopen(Request(base + "/v1/routes")) as result:
            route = json.loads(result.read())["data"][0]
        self.assertEqual(route["executionScope"], "local")
        self.assertEqual(route["dataResidency"], "device")
        self.assertFalse(route["networkRequired"])
        self.assertTrue(route["local"])


if __name__ == "__main__":
    unittest.main()
