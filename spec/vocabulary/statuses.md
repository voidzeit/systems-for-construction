# SFC status vocabulary

## Determination

`MET`, `NOT_MET`, `NOT_APPLICABLE`, `INCOMPLETE`, `UNKNOWN`, `STALE`

`MET`, `NOT_MET` and `NOT_APPLICABLE` close a requirement; the rest leave it
open. `NOT_APPLICABLE` is not a form of compliance: it records that the
requirement was excluded, and it is reachable only when the population is empty
*and* the non-applicability is itself evidenced. See ADR 0007.

Every non-obvious status carries machine-readable `reasons`:

| Reason | Meaning |
| --- | --- |
| `EMPTY_POPULATION_UNRESOLVED` | Nothing matched the population and applicability is unresolved. |
| `EMPTY_POPULATION_APPLICABILITY_UNEVIDENCED` | The author declared the `not_applicable` policy but cited no evidence. |
| `POPULATION_BELOW_MINIMUM` | Fewer subjects than `minimumExpected` were found. |
| `NOT_APPLICABLE_EVIDENCED` | Non-applicability is evidenced, so the empty population closes. |
| `MISSING_OBSERVATION` | A subject carried no value for the requested property. |
| `PREDICATE_NOT_EVALUABLE` | A value existed but the predicate could not be applied to it. |
| `UNRESOLVED_MEASUREMENT_UNIT` | Exactly one side of the comparison declared a unit. |
| `UNKNOWN_MEASUREMENT_UNIT` | A unit was declared that SFC cannot express. |
| `INCOMPATIBLE_MEASUREMENT_DIMENSION` | Both units were known and measured different dimensions. |

The same codes appear on each unresolved subject, alongside the evidence that
was inspected without deciding it. See ADR 0007 and ADR 0008.

## Obligation

`discovered → classified → accepted → allocated → in_progress → claimed_satisfied → verified → approved`

## Work package

`planned → in_progress → evidence_claimed → verified → approved → closed`

## Value

`Unbudgeted → Budgeted → Committed → Planned → Earned → Certified → Billed → Approved for Payment → Paid → Collected`

Transitions are explicit and sequential. A connector or agent may propose a
transition, but an application service must enforce the deterministic graph
and record the event.

