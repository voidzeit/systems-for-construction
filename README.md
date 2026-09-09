# Systems for Construction

> **Open infrastructure for construction intelligence.**

Construction information is fragmented across models, drawings, schedules, project systems and financial systems. AI can reason over pieces of that information, but engineering decisions need evidence, provenance and deterministic authority.

SFC is an open-source runtime for connecting obligations, work, agents, project evidence and governed determinations across the construction lifecycle.

```text
Obligation
    ↓
Project World
    ↓
Engineering Agent
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

The first executable slice is intentionally small. It evaluates a requirement against a provider-neutral `ProjectWorld`, keeps candidate evidence separate from admitted evidence, records a reproducible run, and publishes a result atomically.

## Quick start

The CLI uses only the Python standard library for the core workflow.

```bash
python -m pip install -e .
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
python -m sfc.mcp
```

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
- A failed run cannot replace the last valid canonical publication.
- Every fact has provenance, and every determination identifies its population and coverage.
- Missing measurements stay missing. They are never reported as zero.

## Status

SFC is alpha software. The current slice provides the deterministic contracts and runtime foundation. IFC/PDF/Revit connectors, durable service deployment and the Studio application are extension points, not hidden claims of completeness.

See [ARCHITECTURE.md](ARCHITECTURE.md), [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/adr/](docs/adr/) for the public design record.
