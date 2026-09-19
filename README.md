# Systems for Construction

> **Open infrastructure for construction intelligence.**

Construction information is fragmented across models, drawings, schedules, project systems and financial systems. AI can reason over pieces of that information, but engineering decisions need evidence, provenance and deterministic authority.

SFC is an open-source runtime for connecting obligations, work, engineering intelligence, project evidence and governed determinations across the construction lifecycle.

```text
Obligation
    ↓
Project World
    ↓
Engineering Intelligence
    ↓
Candidate Evidence
    ↓
Admitted Evidence
    ↓
Proof
    ↓
Determination
    ↓
Canonical Run
```

The reference runtime evaluates requirements against a provider-neutral
`ProjectWorld`, imports common IFC STEP property sets and relationships without
Autodesk, runs bounded multi-turn investigations, keeps candidate evidence
separate from admitted evidence, records reproducible runs, and publishes
results atomically.

## Quick start

The CLI uses only the Python standard library for the core workflow.

```bash
python -m pip install -e ".[dev]"   # or: pip install -e .  for the stdlib-only runtime
python -m sfc verify \
  examples/electrical-panel-clearance/requirement.json \
  examples/electrical-panel-clearance/project-world.json \
  --output examples/electrical-panel-clearance/run.json
```

The example contains 18 panels, 17 conforming observations and one counterexample. Missing observations remain incomplete; they are never converted into a failure merely because evidence is absent.

Other commands:

```bash
python -m sfc inspect examples/electrical-panel-clearance/project-world.json
python -m sfc doctor
python -m sfc support-bundle --output support-bundle.zip
python -m sfc ifc-import model.ifc --output .sfc/project-world.json
python -m sfc pdf-import drawings.pdf --output .sfc/drawing-world.json
python -m sfc admit-evidence evidence.json --output .sfc/admitted-evidence.json
python -m sfc investigate model.ifc --statement "Every electrical distribution board must maintain 36 inches of working clearance" --output .sfc/investigation.json
python -m sfc investigate model.ifc --statement "Every electrical distribution board must maintain 36 inches of working clearance" --provider environment
python -m sfc report .sfc/canonical-run.json --format html --output report.html
python -m sfc readiness .sfc/canonical-run.json --evidence .sfc/evidence.json --output .sfc/readiness.json
python -m sfc serve --world .sfc/project-world.json --run .sfc/canonical-run.json --evidence .sfc/evidence.json --events .sfc/events.jsonl
python -m sfc gateway --port 8790
python -m sfc.mcp
```

Grouped aliases are additive and keep the flat commands compatible:

```bash
python -m sfc project inspect examples/electrical-panel-clearance/project-world.json
python -m sfc requirements check examples/electrical-panel-clearance/requirement.json examples/electrical-panel-clearance/project-world.json
python -m sfc work inspect examples/work-unit-feeder/work-unit.json
python -m sfc plugins inspect examples/plugin-reference-electrical/plugin.json
python -m sfc plugins list --path examples/plugin-reference-electrical
```

The `reference` investigation provider is deterministic and offline. Use
`--provider environment` to select an HTTP adapter through `SFC_PROVIDER`,
`SFC_MODEL` and the matching provider credential environment variable.

The local API serves the read-only Studio at `/` plus `/health`, `/project`,
`/elements`, `/run`, `/readiness`, `/activity` and `/tasks`. Stable deep links are available
at `/projects/{projectId}/elements/{elementId}`, `/evidence/{evidenceId}`,
`/requirements/{requirementId}` and `/runs/{runId}`. The MCP gateway provides equivalent inspection tools
for Project World, elements, relationships, evidence, requirements, runs and
measurements.

The SFC AI Gateway serves OpenAI-shaped `/v1/chat/completions`,
`/v1/responses` and `/v1/embeddings` endpoints plus model, provider, route,
usage and health views. It exposes logical models and keeps a provider ledger;
see [docs/concepts/ai-gateway.md](docs/concepts/ai-gateway.md).

## Repository shape

```text
spec/                 Versioned, portable SFC contracts
packages/sfc-core/    Provider-neutral domain and runtime
connectors/           IFC, PDF and Revit integration boundaries
providers/            LLM and vision provider boundaries
tools/                CLI and protocol entry points
examples/             Small public reference projects
tests/                Deterministic regression tests
docs/                 Concepts, architecture and ADRs
```

The core does not import FastAPI, SQLAlchemy, Autodesk SDKs, cloud SDKs or a model provider. Adapters can depend on the core contracts; the core does not depend on adapters.

## Governing principles

- AI proposes; evidence supports; policy governs; authority approves; events record.
- Candidate evidence is not admitted evidence.
- Absence of evidence is not evidence of absence.
- Agents may investigate and propose, but they cannot publish or approve.
- SFC orchestrates work, not agents: agents, models and tools are replaceable executors of governed Work Units.
- A failed run cannot replace the last valid canonical publication.
- Every fact has provenance, and every determination identifies its population and coverage.
- Missing measurements stay missing. They are never reported as zero.
- A quantifier closes on the terms it claims: a universal claim needs the whole
  population, an existential claim needs one named witness.
- Evidence a determination rests on is never conflated with evidence merely
  inspected on a subject it could not decide.

## Status

SFC is alpha software. The current slice provides deterministic contracts,
runtime, a conservative IFC STEP reader, optional PDF extraction, bounded agent
contracts, provider adapters, a local read-only API, a Studio reference page,
benchmarks and an MCP gateway. Production Revit coverage, durable service
deployment and enterprise control plane features remain extension points.

The reference control plane and evidence room are **in-memory**: they define
what a valid transition is, and their state is gone when the process ends. The
append-only event log is what persists, and both projections reduce back from
it - `ControlPlane.from_events` and `EvidenceRoom.from_events` - applying the
same rules as live execution, so an invalid log fails to replay rather than
reconstructing a forbidden state, and a log carrying an event type the build
cannot read is refused rather than reduced into a state that omits it.

What the log is **not** yet: tamper-evident. It is append-only by convention
rather than by construction, so removing a line leaves no trace. A hash chain
and stream versioning for concurrent writers belong to a durable deployment
layer, along with multi-tenancy and identity; they are deliberately not part of
SFC Core.

The contract has two layers, and both are executed. `spec/*.schema.json`
decides shape; `sfc.conformance` decides whether the fields can mean anything
together - that coverage describes the counts it summarises, that supporting
and inspected evidence stay disjoint, that a run's proof is a proof of that
run's determination. `RunStore.publish` applies both, so an adapter writing
JSON directly cannot publish a document that is well-formed and semantically
impossible. See [spec/README.md](spec/README.md) for the invariants a producer
in another language has to satisfy.

See [ARCHITECTURE.md](ARCHITECTURE.md), [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/adr/](docs/adr/) for the public design record.
