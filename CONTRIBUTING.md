# Contributing to SFC

Keep changes small, deterministic and provider-neutral. Domain code belongs under `packages/sfc-core`; integrations belong under `connectors/` or `providers/`.

Before opening a pull request:

```bash
python -m unittest discover -s tests -v
python -m sfc doctor
```

New behavior should include a focused regression test and, where it changes a public contract, a schema or ADR update. Do not commit customer files, real drawings, RVT files, credentials, absolute machine paths or copied private transcripts.

