# SFC AI Gateway

SFC exposes a provider-neutral gateway at `/v1`. Clients can use logical
models such as `sfc/engineering-fast`, while the gateway selects a registered
provider route and records the invocation in its own JSONL ledger.

The reference server supports:

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /v1/embeddings`
- `GET /v1/models`, `/v1/providers`, `/v1/routes`, `/v1/usage`, `/v1/health`

The default gateway is deterministic and offline. Set
`SFC_GATEWAY_PROVIDER=environment` to use the existing HTTP adapters selected
by `SFC_PROVIDER` (`openai-compatible`, `anthropic` or `gemini`). Set
`SFC_GATEWAY_API_KEY` to require a bearer key and `SFC_GATEWAY_LOCAL_ONLY=true`
to reject non-local routes.

The gateway routes model calls only. Evidence admission, assurance and
canonical publication remain SFC application responsibilities.
