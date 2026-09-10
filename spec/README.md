# SFC Specifications

These JSON Schema 2020-12 documents are the portable boundary between SFC
and connectors, providers, applications and external tools. The schemas are
deliberately independent of Python classes and persistence technology.

The initial schemas describe the first public vocabulary. Backward-incompatible
contract changes require a new schema version and an ADR.

## These schemas are executed, not just published

`tests/conformance/` validates every artifact SFC produces against the schema
that describes it, in both directions:

```
python object -> JSON -> schema -> python object -> JSON   (round-trip)
schema fixture -> python object -> JSON -> schema          (fixture direction)
```

The suite covers the example obligations, a compiled obligation, determinations
in every closing and non-closing state, the published run on disk and at the
canonical pointer, proofs, admitted evidence with its measurement audit, reviews,
values, work packages, and every event the reference control plane emits. It also
checks that each schema is a valid Draft 2020-12 document, declares an `$id`
matching its filename, and that cross-file `$ref`s resolve.

Run it with the development extra installed:

```bash
pip install -e ".[dev]"
python -m unittest discover -s tests/conformance -t .
```

`jsonschema` is a development dependency only — SFC Core stays stdlib-only by
ADR 0001, and a second CI job asserts that the runtime works with no
third-party package installed. In CI the conformance job sets
`SFC_REQUIRE_CONFORMANCE=1`, which makes a missing `jsonschema` a failure rather
than a skip, so schema drift can never pass unnoticed.

