# SFC AI Gateway

SFC exposes a provider-neutral gateway at `/v1`. Clients can use logical
models such as `sfc/engineering-fast`, while the gateway selects a registered
provider route and records the invocation in its own JSONL ledger.

The reference server supports:

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/embeddings`
- `GET /v1/models`, `/v1/providers`, `/v1/routes`, `/v1/policy`, `/v1/usage`, `/v1/health`

The default gateway is deterministic and offline. Set
`SFC_GATEWAY_PROVIDER=environment` to add the HTTP adapters selected by
`SFC_PROVIDER` (`openai-compatible`, `anthropic` or `gemini`), and
`SFC_GATEWAY_API_KEY` to require a bearer key.

## A route declares where it runs

Privacy is a property of a route, not of its name. Every route declares three
things, and policy is evaluated against those rather than against a provider or
model name:

| Property | Values | Meaning |
| --- | --- | --- |
| `executionScope` | `local`, `private_cloud`, `public_cloud` | where the model actually runs |
| `dataResidency` | `device`, `region`, `external` | how far the prompt travels |
| `networkRequired` | boolean | whether the call leaves the process |

A route is local only when all three hold: `local` scope, `device` residency and
no network. `GET /v1/routes` publishes them, so a client can check what a route
is rather than trusting what it is called.

```json
{
  "routeId": "route-local-private",
  "executionScope": "local",
  "dataResidency": "device",
  "networkRequired": false,
  "local": true
}
```

`sfc/local-private` is always served by the in-process reference provider, even
when an upstream provider is configured. The name is a claim the gateway can
keep.

## Policy

| Variable | Effect |
| --- | --- |
| `SFC_GATEWAY_LOCAL_ONLY=true` | only routes that are local on all three properties |
| `SFC_GATEWAY_EXECUTION_SCOPES=local,private_cloud` | permitted execution scopes |
| `SFC_GATEWAY_MAX_DATA_RESIDENCY=region` | permitted residency, and everything closer to the device |
| `SFC_GATEWAY_EXECUTION_SCOPE`, `SFC_GATEWAY_DATA_RESIDENCY` | what the configured upstream actually is |
| `SFC_GATEWAY_ROUTING` | `quality`, `cost` or `latency` |

The last pair matters for a self-hosted deployment. An on-premise vLLM behind
`SFC_PROVIDER=openai-compatible` is not a public cloud, and declaring
`SFC_GATEWAY_EXECUTION_SCOPE=private_cloud` with
`SFC_GATEWAY_DATA_RESIDENCY=region` lets a `confidential` project use it. It is
still not `local`, because the prompt leaves the machine.

A request may also carry per-call metadata:

```json
{"model": "sfc/engineering-deep", "messages": [...],
 "metadata": {"projectSensitivity": "restricted", "runId": "run-abc"}}
```

| Sensitivity | Permitted execution scopes |
| --- | --- |
| `restricted` | `local` |
| `confidential` | `local`, `private_cloud` |
| `unrestricted` | any |

An unrecognized sensitivity is refused rather than ignored. Reading a misspelled
value as "no limit" would turn a typo into an outbound data path, so a caller
that wants no constraint states `unrestricted` explicitly.

## What the gateway is not

The gateway routes model calls only. Evidence admission, assurance and canonical
publication remain SFC application responsibilities, and a provider response is
never authoritative evidence by itself. Fallback between routes is infrastructure
behavior: it is recorded in the usage ledger and never enters a determination.

The reference gateway is a single process with an in-memory registry and a local
ledger. Durable multi-tenant policy, quota enforcement and per-organization
routing belong to a deployment layer built on these contracts, not to SFC Core.
