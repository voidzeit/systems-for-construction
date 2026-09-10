# ADR 0007: An empty population may close only when non-applicability is evidenced

## Status

Accepted.

## Context

`ADR 0003: absence is not failure` established that a missing observation must not
be reported as a violation. The mirror case was left open: what does it mean when
the *population* itself is empty — when no subject matches the obligation at all?

Classical logic answers that `∀x ∈ ∅, P(x)` is true. The first implementation
followed that answer literally: an obligation whose population matched nothing
produced `coverage = 1.0` and `MET`.

For an engineering determination published as an authority, that answer is wrong.
Zero matched subjects is ambiguous across at least five situations:

- the requirement genuinely does not apply to this project;
- the model does not contain those elements yet;
- the connector did not import that family of elements;
- the element kind is misspelled or mapped to the wrong canonical term;
- the discipline was never loaded into the snapshot.

Only the first is compliance. The other four are gaps in the evidence base. A
system that returns `MET` for all five reports a false closure whenever the
population is empty for a mechanical reason — which is precisely the failure mode
`falseClosureRate` exists to measure.

## Decision

An empty population never closes on its own. Closure requires that the
non-applicability itself be evidenced.

Obligations carry an optional applicability declaration on the population:

```json
"population": {
  "kind": "electrical_distribution_board",
  "minimumExpected": 1,
  "emptyPopulationPolicy": "not_applicable",
  "applicability": {
    "applicable": false,
    "evidenceIds": ["E-SCOPE-ELECTRICAL-NONE"],
    "basis": "contract scope excludes electrical distribution"
  }
}
```

The kernel resolves an empty population as follows:

```
expected population = 0
        |
        +-- applicable == false AND evidenceIds non-empty
        |        -> NOT_APPLICABLE          (reason NOT_APPLICABLE_EVIDENCED)
        |
        +-- applicability unresolved
                 -> INCOMPLETE             (reason EMPTY_POPULATION_UNRESOLVED,
                                            or EMPTY_POPULATION_APPLICABILITY_UNEVIDENCED
                                            when the author declared the
                                            not_applicable policy without evidence)
```

Three further rules follow from the same principle:

1. `NOT_APPLICABLE` is a new closing status, distinct from `MET`. A requirement
   that does not apply was never satisfied; it was excluded, and the exclusion has
   a cited basis a reviewer can check.
2. `emptyPopulationPolicy` declares intent only. It cannot bypass the evidence
   requirement — intent alone never closes a requirement.
3. `minimumExpected` states how many subjects the requirement presupposes. A
   population smaller than that never closes, even when every subject that *was*
   found conforms. Three conforming boards where the requirement presupposes five
   is an incomplete evaluation, not compliance.

`coverage` becomes nullable. With no expected population there is nothing to
cover, so coverage is `null` rather than `1.0`, consistent with the usage ledger's
rule that an unavailable measurement is omitted rather than recorded as zero.

## Consequences

- `validate_determination` rejects `MET` with an empty population, and rejects
  `NOT_APPLICABLE` without applicability evidence or with a non-empty population.
  Because `RunStore.publish` validates before moving the canonical pointer, a
  vacuously closed determination cannot be published.
- Consumers gain a status. `CLOSING_STATUSES` is exported so callers can ask
  whether a requirement is closed without enumerating statuses; the CLI exits `0`
  for any closing status.
- Determinations carry `reasons`, a list of machine-readable codes. A reviewer
  reading `INCOMPLETE` learns whether the population was empty, below the declared
  minimum, missing observations, or carried a predicate that could not be
  evaluated.
- Existing obligations keep working. With no applicability block and no declared
  minimum, an empty population reports `INCOMPLETE` instead of `MET` — a
  deliberate behavioral change, and the point of this ADR.

## Alternatives considered

**Keep vacuous truth and document it.** Rejected: the semantics of a published
engineering determination should not require the consumer to know that `MET` may
mean "nothing was examined".

**Introduce a `VACUOUS` status.** Rejected as the primary mechanism: it forces
every consumer to learn another status while still not distinguishing "does not
apply" from "was not loaded". `INCOMPLETE` already carries the correct meaning
for an unresolved population, and the `reasons` codes carry the detail.

**Infer applicability from project metadata.** Rejected: inference would
reintroduce the guess this ADR removes. Non-applicability is a claim about the
project, and claims need evidence.
