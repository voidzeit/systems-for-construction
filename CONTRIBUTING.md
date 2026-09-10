# Contributing to SFC

Keep changes small, deterministic and provider-neutral. Domain code belongs under `packages/sfc-core`; integrations belong under `connectors/` or `providers/`.

## Getting a working checkout

```bash
git clone https://github.com/your-fork/systems-for-construction
cd systems-for-construction
python -m venv .venv && . .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Both runners work, with or without an install: `pytest` finds the package through
`pythonpath` in `pyproject.toml`, and `python -m unittest discover -s tests` works
once the package is installed. The `dev` extra adds `jsonschema` and `pytest`; the
runtime itself stays stdlib-only by ADR 0001, and `tests/test_stdlib_only.py`
enforces that.

## Before opening a pull request

```bash
pytest
SFC_REQUIRE_CONFORMANCE=1 python -m unittest discover -s tests/conformance -t .
SFC_REQUIRE_CONFORMANCE=1 python -m unittest tests.test_release_gate
python -m sfc doctor
```

`tests/test_release_gate.py` is the one place the whole guarantee is written
down as an executable statement, so read it before changing anything the
determination pipeline asserts.

New behavior should include a focused regression test and, where it changes a
public contract, a schema or ADR update.

## Boundaries enforced by tests rather than by review

A change that crosses one of these fails rather than passing quietly:

| Boundary | Enforced by |
| --- | --- |
| The runtime imports only the standard library | `tests/test_stdlib_only.py` |
| Every published artifact matches its schema in `spec/` | `tests/conformance/` |
| Document invariants JSON Schema cannot express | `tests/test_conformance_semantics.py` |
| Each quantifier closes on its own terms, and publishes | `tests/test_quantifier_closure.py` |
| Both projections rebuild from the event log | `tests/test_evidence_room_replay.py`, `tests/test_control_plane_replay.py` |
| The assurance kernel names no discipline term | `tests/test_vocabulary.py` |
| The CLI exit codes, artifacts and stdout | `tests/test_cli.py` |
| Coverage does not regress below its floors | `tools/coverage_gate.py` |

## Coverage

Coverage is a regression net, not a definition of quality: a suite can walk the
same code repeatedly and still say nothing about whether the engineering
semantics are exercised. So the target is a semantic case, not a percentage -
an empty population with no evidenced applicability, an unknown unit, an
incompatible dimension, `ALL` with one counterexample and several unknowns,
stale admitted evidence, a log with an unreadable event - and the number is
there only to notice when something that used to be exercised stops being.

```bash
python -m coverage run -m unittest discover -s tests -t . -q
python -m coverage json -o coverage.json
python tools/coverage_gate.py coverage.json
```

The gate applies a floor over the whole runtime and a higher one to the modules
that decide what SFC asserts. Raise a floor when the measurement rises; do not
lower one to make a change pass.

Do not commit customer files, real drawings, RVT files, credentials, absolute
machine paths or copied private transcripts.

