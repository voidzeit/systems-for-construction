# ADR 0010: Route privacy is a declared property, not a name

## Status

Accepted.

## Context

The gateway had one privacy signal, a boolean `local` on each route, and
`build_default_gateway` set it by inference:

```python
local=provider_name == "reference"
```

With `SFC_GATEWAY_PROVIDER=environment`, `provider_name` becomes the configured
upstream, so every route — including `sfc/local-private` — was marked
`local=False`. Two things followed.

First, the name lied. A client selecting `sfc/local-private` for a sensitive
project was routed to whatever `SFC_PROVIDER` pointed at, which could be a
public API. The route promised confidentiality the policy did not deliver.

Second, `SFC_GATEWAY_LOCAL_ONLY=true` left **zero** usable routes. The one
setting an operator would reach for to keep data on the machine disabled the
gateway entirely, which invites turning it off rather than fixing it.

Underneath both: `local` conflated three separate questions. Where does the
model run? How far does the prompt travel? Does the call leave the process? A
self-hosted model in the operator's own region is not a public cloud, and it is
not on the device either. One boolean cannot say that.

## Decision

A route declares its deployment properties, and policy is evaluated against
those rather than against a provider or model name.

```
execution_scope   local | private_cloud | public_cloud     where the model runs
data_residency    device | region | external               how far the prompt travels
network_required  bool                                     whether the call leaves the process
```

`local` becomes derived, and requires all three:

```python
is_local = (execution_scope is LOCAL
            and data_residency is DEVICE
            and not network_required)
```

It is still published in `to_dict()` and over `/v1/routes`, so clients keep a
single field to read, but it can no longer be asserted independently of the
properties it summarizes.

### The default build tells the truth

The in-process reference provider is registered always, and
`sfc/local-private` always routes to it. An upstream provider is added
*alongside* when configured, carrying the properties it actually has. So:

- `sfc/local-private` is local in every configuration;
- `SFC_GATEWAY_LOCAL_ONLY=true` leaves a working route rather than none;
- a model with no local route is refused with a `GatewayError` that names the
  scope and residency of the route it rejected, rather than failing silently.

A self-hosted deployment can declare what it is through
`SFC_GATEWAY_EXECUTION_SCOPE` and `SFC_GATEWAY_DATA_RESIDENCY`, so an
on-premise model becomes usable for a `confidential` project without being
misdescribed as `local`.

### Sensitivity fails closed

Project sensitivity maps to permitted execution scopes:

| Sensitivity | Permitted scopes |
| --- | --- |
| `restricted` | `local` |
| `confidential` | `local`, `private_cloud` |
| `unrestricted` | any |

An unrecognized value raises instead of being ignored. The previous code
compared `projectSensitivity == "restricted"` exactly, so `"Restricted"` or a
typo silently granted full access — a misspelling became an outbound data path.
A caller that wants no constraint now says `unrestricted`.

## Consequences

- The `local=` constructor argument is gone. Call sites pass the `IN_PROCESS`
  properties, which is longer to write and impossible to misread.
- `GET /v1/policy` reports the active policy without revealing the key, so an
  operator can confirm what is enforced instead of inferring it from behavior.
- The API key is compared with `secrets.compare_digest`. The gateway binds to
  `127.0.0.1` by default, which makes a timing attack unlikely rather than
  impossible, and the fix is one call.
- `sfc-enterprise` gets a policy surface to build on. "This project is
  restricted, therefore execution scope must be local" is expressible against
  declared route properties, and does not depend on how a provider was named.

## Alternatives considered

**Keep `local` and set it correctly.** Rejected: it would fix this instance and
leave the conflation. A private-cloud deployment still has no way to describe
itself, so the next operator with an on-premise model faces the same choice
between lying and losing access.

**Infer properties from the base URL — treat `localhost` as local.** Rejected
for the same reason as the provider-name inference. A hostname is not an
enforceable property either, and an SSH tunnel to a public endpoint looks like
`localhost`.

**Drop `sfc/local-private` and let operators register their own routes.**
Rejected: the logical model is useful, and the fix is to make the guarantee real
rather than to remove the name that carried it.
