"""Provider-neutral SFC AI Gateway reference implementation.

The gateway normalizes model calls at an infrastructure boundary. It does not
make engineering determinations and it never turns a provider response into
authoritative evidence by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
import hashlib
import json
import os
import secrets
import time
import uuid

from . import __version__
from .http_providers import ProviderError, provider_from_environment
from .providers import EngineeringProvider, ProviderRequest, ProviderResponse
from .telemetry import UsageLedger


class EmbeddingProvider(Protocol):
    def embed(self, inputs: list[str], model: str) -> list[list[float]]: ...


class ExecutionScope(StrEnum):
    """Where the model actually runs."""

    LOCAL = "local"
    PRIVATE_CLOUD = "private_cloud"
    PUBLIC_CLOUD = "public_cloud"


class DataResidency(StrEnum):
    """How far the prompt travels."""

    DEVICE = "device"
    REGION = "region"
    EXTERNAL = "external"


#: Increasing distance from the device. A policy that permits a residency also
#: permits everything closer to the device.
RESIDENCY_DISTANCE = {DataResidency.DEVICE: 0, DataResidency.REGION: 1, DataResidency.EXTERNAL: 2}

#: Execution scopes a project sensitivity permits. Sensitivity is a statement
#: about the project, and it constrains routing regardless of provider names.
#: A caller that wants no constraint must say so, because a sensitivity the
#: gateway does not recognize is refused rather than read as "no limit".
SENSITIVITY_SCOPES: dict[str, frozenset[ExecutionScope]] = {
    "restricted": frozenset({ExecutionScope.LOCAL}),
    "confidential": frozenset({ExecutionScope.LOCAL, ExecutionScope.PRIVATE_CLOUD}),
    "unrestricted": frozenset(ExecutionScope),
}


@dataclass(frozen=True)
class GatewayRoute:
    """One way to reach a model, with its deployment properties declared.

    execution_scope, data_residency and network_required are what a policy is
    evaluated against. They are declared per route rather than inferred from a
    provider or model name, because a name is not an enforceable property: a
    route named local-private that reaches a public API is a promise the gateway
    cannot keep.
    """

    route_id: str
    logical_model: str
    provider: str
    upstream_model: str
    quality_score: float | None = None
    false_closure_rate: float | None = None
    cost_per_1k_tokens: float | None = None
    latency_ms: float | None = None
    capabilities: tuple[str, ...] = ("chat", "responses")
    execution_scope: ExecutionScope = ExecutionScope.PUBLIC_CLOUD
    data_residency: DataResidency = DataResidency.EXTERNAL
    network_required: bool = True

    @property
    def is_local(self) -> bool:
        """Local means all three: on this machine, on this device, offline."""
        return (
            self.execution_scope is ExecutionScope.LOCAL
            and self.data_residency is DataResidency.DEVICE
            and not self.network_required
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "routeId": self.route_id,
            "model": self.logical_model,
            "provider": self.provider,
            "upstreamModel": self.upstream_model,
            "qualityScore": self.quality_score,
            "falseClosureRate": self.false_closure_rate,
            "costPer1kTokens": self.cost_per_1k_tokens,
            "latencyMs": self.latency_ms,
            "executionScope": self.execution_scope.value,
            "dataResidency": self.data_residency.value,
            "networkRequired": self.network_required,
            "local": self.is_local,
            "capabilities": list(self.capabilities),
        }


#: Deployment properties of a provider that runs in this process and reaches
#: nothing. Spread into a GatewayRoute for a genuinely local route.
IN_PROCESS = {
    "execution_scope": ExecutionScope.LOCAL,
    "data_residency": DataResidency.DEVICE,
    "network_required": False,
}


class GatewayError(RuntimeError):
    pass


class ProviderRegistry:
    def __init__(self) -> None:
        self.providers: dict[str, EngineeringProvider] = {}
        self.embedding_providers: dict[str, EmbeddingProvider] = {}
        self.routes: list[GatewayRoute] = []

    def register_provider(self, name: str, provider: EngineeringProvider, *, embedding_provider: EmbeddingProvider | None = None) -> None:
        self.providers[name] = provider
        if embedding_provider is not None:
            self.embedding_providers[name] = embedding_provider

    def register_route(self, route: GatewayRoute) -> None:
        if route.provider not in self.providers:
            raise ValueError(f"provider is not registered: {route.provider}")
        self.routes.append(route)

    def routes_for(self, logical_model: str, capability: str = "chat") -> list[GatewayRoute]:
        return [route for route in self.routes if route.logical_model == logical_model and capability in route.capabilities]

    def models(self) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for route in self.routes:
            item = seen.setdefault(route.logical_model, {"id": route.logical_model, "object": "model", "owned_by": "sfc", "routes": []})
            item["routes"].append(route.route_id)
        return list(seen.values())

    def providers_view(self) -> list[dict[str, Any]]:
        return [{"id": name, "status": "registered", "capabilities": sorted({cap for route in self.routes if route.provider == name for cap in route.capabilities})} for name in self.providers]


@dataclass(frozen=True)
class GatewayPolicy:
    allowed_providers: frozenset[str] = frozenset()
    allowed_models: frozenset[str] = frozenset()
    local_only: bool = False
    required_execution_scopes: frozenset[ExecutionScope] = frozenset()
    maximum_data_residency: DataResidency | None = None
    routing_strategy: str = "quality"
    api_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowedProviders": sorted(self.allowed_providers),
            "allowedModels": sorted(self.allowed_models),
            "localOnly": self.local_only,
            "requiredExecutionScopes": sorted(scope.value for scope in self.required_execution_scopes),
            "maximumDataResidency": None if self.maximum_data_residency is None else self.maximum_data_residency.value,
            "routingStrategy": self.routing_strategy,
            "apiKeyRequired": bool(self.api_key),
        }

    def authorize(self, route: GatewayRoute) -> None:
        if self.allowed_providers and route.provider not in self.allowed_providers:
            raise PermissionError(f"provider is not allowed: {route.provider}")
        if self.allowed_models and route.logical_model not in self.allowed_models:
            raise PermissionError(f"model is not allowed: {route.logical_model}")
        if self.local_only and not route.is_local:
            raise PermissionError(
                f"policy requires a local route; {route.route_id} runs "
                f"{route.execution_scope.value} with {route.data_residency.value} data residency"
            )
        if self.required_execution_scopes and route.execution_scope not in self.required_execution_scopes:
            permitted = sorted(scope.value for scope in self.required_execution_scopes)
            raise PermissionError(
                f"policy requires execution scope in {permitted}; "
                f"{route.route_id} runs {route.execution_scope.value}"
            )
        if self.maximum_data_residency is not None and RESIDENCY_DISTANCE[route.data_residency] > RESIDENCY_DISTANCE[self.maximum_data_residency]:
            raise PermissionError(
                f"policy permits data residency up to {self.maximum_data_residency.value}; "
                f"{route.route_id} sends data {route.data_residency.value}"
            )


class ProviderRouter:
    def __init__(self, registry: ProviderRegistry, policy: GatewayPolicy | None = None) -> None:
        self.registry = registry
        self.policy = policy or GatewayPolicy()

    def candidates(self, logical_model: str, *, capability: str = "chat", metadata: dict[str, Any] | None = None) -> list[GatewayRoute]:
        metadata = metadata or {}
        routes = self.registry.routes_for(logical_model, capability)
        routes = [route for route in routes if self._allowed(route)]
        if metadata.get("localOnly"):
            routes = [route for route in routes if route.is_local]
        routes = self._within_sensitivity(routes, metadata.get("projectSensitivity"))
        strategy = str(metadata.get("routingStrategy", self.policy.routing_strategy))
        if strategy == "cost":
            return sorted(routes, key=lambda route: (route.cost_per_1k_tokens is None, route.cost_per_1k_tokens or float("inf")))
        if strategy == "latency":
            return sorted(routes, key=lambda route: (route.latency_ms is None, route.latency_ms or float("inf")))
        if strategy == "quality":
            return sorted(routes, key=lambda route: (route.quality_score is None, -(route.quality_score or 0), route.false_closure_rate is None, route.false_closure_rate or float("inf")))
        return routes

    @staticmethod
    def _within_sensitivity(routes: list[GatewayRoute], sensitivity: Any) -> list[GatewayRoute]:
        """Constrain routing by how sensitive the project is.

        A misspelled or unknown sensitivity fails closed. Reading it as "no
        limit" would turn a typo into an outbound data path.
        """
        if sensitivity is None:
            return routes
        normalized = str(sensitivity).strip().lower().replace("-", "_")
        if not normalized:
            return routes
        permitted = SENSITIVITY_SCOPES.get(normalized)
        if permitted is None:
            known = ", ".join(sorted(SENSITIVITY_SCOPES))
            raise GatewayError(f"unknown project sensitivity: {sensitivity!r}; known values are {known}")
        return [route for route in routes if route.execution_scope in permitted]

    def _allowed(self, route: GatewayRoute) -> bool:
        try:
            self.policy.authorize(route)
        except PermissionError:
            return False
        return True

    def select(self, logical_model: str, *, capability: str = "chat", metadata: dict[str, Any] | None = None) -> GatewayRoute:
        routes = self.candidates(logical_model, capability=capability, metadata=metadata)
        if not routes:
            raise ValueError(f"no route available for model {logical_model} and capability {capability}")
        return routes[0]


class ReferenceEmbeddingProvider:
    """Deterministic local embeddings for development; never an authority signal."""

    dimension = 16

    def embed(self, inputs: list[str], model: str) -> list[list[float]]:
        vectors = []
        for text in inputs:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            values = [int.from_bytes(digest[index:index + 2], "big") / 65535 for index in range(0, self.dimension * 2, 2)]
            vectors.append(values)
        return vectors


class ReferenceChatProvider:
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            text=f"Reference provider received: {request.prompt[:500]}",
            requested_model="sfc-reference",
            observed_model="sfc-reference",
            input_tokens=None,
            output_tokens=None,
        )


class ProviderGateway:
    def __init__(self, registry: ProviderRegistry, *, policy: GatewayPolicy | None = None, ledger: UsageLedger | None = None) -> None:
        self.registry = registry
        self.router = ProviderRouter(registry, policy)
        self.ledger = ledger or UsageLedger()

    def complete(self, *, logical_model: str, prompt: str, tools: tuple[dict[str, Any], ...] = (), metadata: dict[str, Any] | None = None, capability: str = "chat") -> ProviderResponse:
        metadata = metadata or {}
        candidates = self.router.candidates(logical_model, capability=capability, metadata=metadata)
        if not candidates:
            raise GatewayError(f"no route available for model {logical_model}")
        started = time.monotonic()
        retries = 0
        last_error: Exception | None = None
        for index, route in enumerate(candidates):
            try:
                response = self.registry.providers[route.provider].complete(ProviderRequest(prompt=prompt, model=route.upstream_model, metadata=metadata, tools=tools))
                self.ledger.record(invocationId=uuid.uuid4().hex, runId=metadata.get("runId"), workUnitId=metadata.get("workUnitId"), agentId=metadata.get("agentId"), provider=route.provider, model=logical_model, route=route.route_id, inputTokens=response.input_tokens, outputTokens=response.output_tokens, latencyMs=round((time.monotonic() - started) * 1000, 3), retries=retries, fallback=index > 0, outcome="success")
                return response
            except Exception as error:  # fallback is infrastructure behavior, never evidence
                last_error = error
                retries += 1
        self.ledger.record(invocationId=uuid.uuid4().hex, runId=metadata.get("runId"), workUnitId=metadata.get("workUnitId"), agentId=metadata.get("agentId"), provider=candidates[0].provider, model=logical_model, route=candidates[0].route_id, latencyMs=round((time.monotonic() - started) * 1000, 3), retries=retries, fallback=False, outcome="error", error=str(last_error))
        raise GatewayError(f"all routes failed for model {logical_model}: {last_error}") from last_error

    def chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        logical_model = str(payload.get("model", "sfc/engineering-fast"))
        prompt = _messages_to_prompt(payload.get("messages", []))
        tools = _openai_tools_to_generic(payload.get("tools", []))
        response = self.complete(logical_model=logical_model, prompt=prompt, tools=tools, metadata=payload.get("metadata"))
        tool_calls = [{"id": call.call_id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)}} for call in response.tool_calls]
        message: dict[str, Any] = {"role": "assistant", "content": response.text or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return {"id": f"chatcmpl-{uuid.uuid4().hex[:16]}", "object": "chat.completion", "created": int(time.time()), "model": logical_model, "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}], "usage": _usage(response)}

    def responses(self, payload: dict[str, Any]) -> dict[str, Any]:
        logical_model = str(payload.get("model", "sfc/engineering-fast"))
        prompt = _input_to_prompt(payload.get("input", ""))
        tools = _openai_tools_to_generic(payload.get("tools", []))
        response = self.complete(logical_model=logical_model, prompt=prompt, tools=tools, metadata=payload.get("metadata"), capability="responses")
        output: list[dict[str, Any]] = []
        if response.text:
            output.append({"id": f"msg_{uuid.uuid4().hex[:16]}", "type": "message", "status": "completed", "role": "assistant", "content": [{"type": "output_text", "text": response.text}]})
        output.extend({"type": "function_call", "id": f"fc_{call.call_id}", "call_id": call.call_id, "name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)} for call in response.tool_calls)
        return {"id": f"resp_{uuid.uuid4().hex[:16]}", "object": "response", "status": "completed", "model": logical_model, "output": output, "usage": _usage(response)}

    def embeddings(self, payload: dict[str, Any]) -> dict[str, Any]:
        logical_model = str(payload.get("model", "sfc/local-private"))
        inputs = payload.get("input", "")
        values = [inputs] if isinstance(inputs, str) else [str(item) for item in inputs]
        route = self.router.select(logical_model, capability="embeddings", metadata=payload.get("metadata"))
        provider = self.registry.embedding_providers.get(route.provider)
        if provider is None:
            raise GatewayError(f"route has no embedding provider: {route.provider}")
        vectors = provider.embed(values, route.upstream_model)
        return {"object": "list", "data": [{"object": "embedding", "index": index, "embedding": vector} for index, vector in enumerate(vectors)], "model": logical_model, "usage": {"prompt_tokens": None, "total_tokens": None}}


def _messages_to_prompt(messages: list[Any]) -> str:
    chunks = []
    for message in messages:
        if not isinstance(message, dict):
            chunks.append(str(message))
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
        chunks.append(f"{message.get('role', 'user')}: {content}")
    return "\n".join(chunks)


def _input_to_prompt(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _messages_to_prompt(value)
    return json.dumps(value, ensure_ascii=False)


def _openai_tools_to_generic(tools: list[Any]) -> tuple[dict[str, Any], ...]:
    generic = []
    for tool in tools:
        function = tool.get("function", tool) if isinstance(tool, dict) else {}
        if function.get("name"):
            generic.append({"name": function["name"], "description": function.get("description", ""), "input_schema": function.get("parameters", {"type": "object"})})
    return tuple(generic)


def _usage(response: ProviderResponse) -> dict[str, Any]:
    return {"prompt_tokens": response.input_tokens, "completion_tokens": response.output_tokens, "total_tokens": (response.input_tokens + response.output_tokens if response.input_tokens is not None and response.output_tokens is not None else None)}


def build_default_gateway(*, ledger_path: str | Path = ".sfc/gateway-usage.jsonl") -> ProviderGateway:
    """Assemble the reference gateway from the environment.

    The in-process reference provider is always registered, and
    ``sfc/local-private`` always routes to it. An upstream provider is added
    alongside when one is configured, and it carries the deployment properties
    it actually has - a public API is not local because the gateway happens to
    run on a laptop. Consequently ``SFC_GATEWAY_LOCAL_ONLY=true`` still leaves a
    usable route instead of emptying the routing table.
    """
    registry = ProviderRegistry()
    registry.register_provider("reference", ReferenceChatProvider(), embedding_provider=ReferenceEmbeddingProvider())
    registry.register_route(GatewayRoute(
        "route-local-private", "sfc/local-private", "reference", "sfc-reference",
        quality_score=0.7, cost_per_1k_tokens=0.0, latency_ms=1,
        capabilities=("chat", "responses", "embeddings"), **IN_PROCESS,
    ))

    upstream_configured = os.environ.get("SFC_GATEWAY_PROVIDER", "reference") == "environment"
    if upstream_configured:
        provider_name = os.environ.get("SFC_PROVIDER", "openai-compatible")
        registry.register_provider(provider_name, provider_from_environment(), embedding_provider=ReferenceEmbeddingProvider())
        upstream_model = os.environ.get("SFC_MODEL", "")
        # A self-hosted deployment can declare what it really is; the default is
        # the most conservative reading of an outbound HTTP call.
        deployment = {
            "execution_scope": ExecutionScope(os.environ.get("SFC_GATEWAY_EXECUTION_SCOPE", "public_cloud")),
            "data_residency": DataResidency(os.environ.get("SFC_GATEWAY_DATA_RESIDENCY", "external")),
            "network_required": True,
        }
    else:
        provider_name = "reference"
        upstream_model = os.environ.get("SFC_MODEL", "sfc-reference")
        deployment = dict(IN_PROCESS)

    registry.register_route(GatewayRoute(
        "route-engineering-fast", "sfc/engineering-fast", provider_name, upstream_model,
        quality_score=0.75, cost_per_1k_tokens=0.01, latency_ms=100, **deployment,
    ))
    registry.register_route(GatewayRoute(
        "route-engineering-deep", "sfc/engineering-deep", provider_name, upstream_model,
        quality_score=0.9, cost_per_1k_tokens=0.04, latency_ms=500, **deployment,
    ))

    scopes = os.environ.get("SFC_GATEWAY_EXECUTION_SCOPES", "")
    residency = os.environ.get("SFC_GATEWAY_MAX_DATA_RESIDENCY")
    policy = GatewayPolicy(
        api_key=os.environ.get("SFC_GATEWAY_API_KEY"),
        local_only=os.environ.get("SFC_GATEWAY_LOCAL_ONLY") == "true",
        required_execution_scopes=frozenset(ExecutionScope(item.strip()) for item in scopes.split(",") if item.strip()),
        maximum_data_residency=DataResidency(residency) if residency else None,
        routing_strategy=os.environ.get("SFC_GATEWAY_ROUTING", "quality"),
    )
    return ProviderGateway(registry, policy=policy, ledger=UsageLedger(ledger_path))


class GatewayRequestHandler(BaseHTTPRequestHandler):
    gateway: ProviderGateway

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = self.gateway.router.policy.api_key
        if not expected:
            return True
        # Constant time, so a wrong key does not leak its correct prefix.
        return secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {expected}")

    def do_GET(self) -> None:
        if not self._authorized():
            self._send(401, {"error": {"message": "unauthorized", "type": "authentication_error"}})
            return
        path = self.path.split("?", 1)[0]
        if path in {"/v1/health", "/health"}:
            self._send(200, {"status": "ok", "gateway": "sfc", "version": __version__})
        elif path == "/v1/models":
            self._send(200, {"object": "list", "data": self.gateway.registry.models()})
        elif path == "/v1/providers":
            self._send(200, {"object": "list", "data": self.gateway.registry.providers_view()})
        elif path == "/v1/policy":
            self._send(200, self.gateway.router.policy.to_dict())
        elif path == "/v1/routes":
            self._send(200, {"object": "list", "data": [route.to_dict() for route in self.gateway.registry.routes]})
        elif path == "/v1/usage":
            self._send(200, {"object": "list", "data": self.gateway.ledger.read()})
        else:
            self._send(404, {"error": {"message": "not found", "type": "invalid_request_error"}})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(401, {"error": {"message": "unauthorized", "type": "authentication_error"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            path = self.path.split("?", 1)[0]
            if path == "/v1/chat/completions":
                result = self.gateway.chat_completion(payload)
            elif path == "/v1/responses":
                result = self.gateway.responses(payload)
            elif path == "/v1/embeddings":
                result = self.gateway.embeddings(payload)
            else:
                self._send(404, {"error": {"message": "not found", "type": "invalid_request_error"}})
                return
            self._send(200, result)
        except (GatewayError, PermissionError, ValueError, KeyError, TypeError, json.JSONDecodeError, ProviderError) as error:
            self._send(400, {"error": {"message": str(error), "type": "gateway_error"}})

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve_gateway(gateway: ProviderGateway | None = None, host: str = "127.0.0.1", port: int = 8790, *, ledger_path: str | Path = ".sfc/gateway-usage.jsonl") -> None:
    configured = gateway or build_default_gateway(ledger_path=ledger_path)
    handler = type("ConfiguredGatewayHandler", (GatewayRequestHandler,), {"gateway": configured})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"SFC AI Gateway listening on http://{host}:{port}/v1")
    server.serve_forever()
