# SFC Specifications

These JSON Schema 2020-12 documents are the portable boundary between SFC
and connectors, providers, applications and external tools. The schemas are
deliberately independent of Python classes and persistence technology.

The initial schemas describe the first public vocabulary. Backward-incompatible
contract changes require a new schema version and an ADR.

## Two layers, because a contract needs both

```
JSON Schema            shape, types, required fields, enums, cross-file $ref
semantic conformance   invariants that relate one field to another
```

JSON Schema cannot express that the evidence a determination rests on must be
disjoint from the evidence it merely inspected, or that a run's proof must
describe that run's determination. Those are statements about several fields at
once. Left to the producer, they would be a property of one implementation
rather than of the contract, and any adapter writing JSON directly could
reintroduce a document that is well-formed and semantically impossible.

`sfc.conformance` is the reference implementation of the second layer. It is
stdlib-only and reads plain dictionaries, so it applies to documents this
runtime never produced:

```python
from sfc.conformance import validate_semantics

validate_semantics("run.schema.json", document)   # raises ConformanceError
```

`RunStore.publish` applies both layers, so an unpublishable document cannot
reach disk.

### The invariants a producer in any language must satisfy

Population and coverage:

- `population.evaluated` never exceeds `population.expected`, and `conforming`
  never exceeds `population.evaluated`.
- `population.expected == 0` requires `coverage: null`. A fraction of a
  population whose applicability was never established is not a measurement.
- `population.expected > 0` requires a numeric `coverage`, and it must equal
  `evaluated / expected` to the precision it is written at.

Evidence:

- `evidenceIds` is what the determination rests on. `inspectedEvidenceIds` is
  what was examined on subjects that could not be decided. The two are
  disjoint, neither repeats, and every identifier in either list is accounted
  for: inspected evidence must belong to an entry in `unknowns`.

Subjects:

- `witnesses` names the subjects that satisfy the predicate; `counterexamples`
  names those that fail it; `unknowns` names those left undecided. A subject
  appears in at most one of the three, and `witnesses` never outnumbers
  `conforming`.

Closing a status:

- `MET` requires a non-empty population. Absence is not compliance.
- `ALL`, `NONE` and `COUNT` claim something about the whole population, so
  `MET` requires `evaluated == expected` and no undecided subject. `ALL/MET`
  carries no counterexample; `NONE/MET` names no witness.
- `ANY` claims something about one subject, so `MET` requires a named witness
  and nothing more. Undecided and failing subjects do not refute it.
- `ALL/NOT_MET` requires a counterexample. `NONE/NOT_MET` requires a witness.
  `ANY/NOT_MET` requires `evaluated == expected`.
- `NOT_APPLICABLE` requires an empty population and evidence that the
  requirement does not apply.

Runs:

- A run's `proof`, when present, must repeat the determination's
  `requirementId`, `population`, `coverage`, result, evidence, inspected
  evidence and witnesses. A proof that disagrees is a proof of something else.

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
values, work packages, work units, plugin manifests, and every event the reference control plane emits. It also
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



## Work and capability extension contracts

`work-unit.schema.json` is the portable unit-of-production contract. It names the package, capability, dependencies, executor, expected output, acceptance/QA criteria, evidence and lifecycle state without prescribing how work is scheduled or optimized.

`plugin.schema.json` is the open manifest boundary for a capability provider. The manifest declares identity, family, domain, permissions, side effects, autonomy ceiling and evidence/acceptance contracts. It deliberately does not publish private routing weights, customer-specific heuristics or learned production intelligence.

These contracts follow the repository knowledge-exposure rule: **open contract, private advantage**.
