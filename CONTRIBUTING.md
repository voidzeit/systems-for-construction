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
python -m sfc doctor
```

New behavior should include a focused regression test and, where it changes a
public contract, a schema or ADR update.

Four boundaries are enforced by tests rather than by review, so a change that
crosses one fails rather than passing quietly:

| Boundary | Enforced by |
| --- | --- |
| The runtime imports only the standard library | `tests/test_stdlib_only.py` |
| Every published artifact matches its schema in `spec/` | `tests/conformance/` |
| The assurance kernel names no discipline term | `tests/test_vocabulary.py` |
| The CLI's exit codes, artifacts and stdout | `tests/test_cli.py` |

Do not commit customer files, real drawings, RVT files, credentials, absolute
machine paths or copied private transcripts.

