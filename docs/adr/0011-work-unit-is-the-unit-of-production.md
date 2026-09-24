# ADR 0011: The work unit is the unit of production, and whoever submits cannot accept

## Status

Accepted.

## Context

SFC could say whether an obligation was met. It could not say what work was
done to meet it. The only work aggregate was the work package: an identifier, a
title, the obligations it groups, one actor and a status. That is enough to
track that a package exists. It is not enough to govern producing it:

- nothing said what had to be produced, or how anyone would decide the result
  was acceptable;
- nothing said which kind of executor was allowed to do the work, so a model,
  a solver and a person were indistinguishable after the fact;
- nothing pinned the inputs, so work planned on one drawing revision and
  delivered against another looked identical;
- nothing ordered work, so a detail could be started before the route it
  details existed;
- the same actor could advance a package from `in_progress` to `approved`.

The production loop SFC exists to close is

```
obligation -> work -> executor -> output -> review -> acceptance -> correction
```

and the second step had no contract.

## Decision

Add `WorkUnit` (`spec/work-unit.schema.json`, `sfc.work`) as the smallest piece
of production work SFC governs. A work package groups work units; it does not
replace them.

A work unit declares:

```
capability          electrical.route.feeder     what kind of work, not who does it
inputs              E-301 @ IFC, ASI-2          sources pinned to a revision
obligationIds       what the work must satisfy
dependsOn           work that must be accepted first
executorPolicy      allowed kinds + autonomy    human | code | solver | llm | revit | external
expectedOutputs     what a submission must contain
acceptanceCriteria  how acceptance is decided
estimatedEffort     a time Quantity, or null    never read as zero (ADR 0003, ADR 0008)
```

### Lifecycle

```
planned -> ready -> in_progress -> submitted -> accepted
   |         |          |              |
   +-> blocked <--------+              +-> rejected -> in_progress (new attempt)
   |         |
   +---------+-> cancelled
```

`blocked` returns through `ready`, so leaving a block re-checks readiness.

### Rules

1. **Every transition names its actor.**
2. **Work in progress has an executor**, of a kind the policy allows. The
   executor may change only before an attempt starts.
3. **Each entry into `in_progress` is a new attempt.** Rework starts with no
   outputs; the rejected outputs remain on the rejected state and in the event
   log, so the review that refused them stays legible.
4. **A submission names its outputs.** `submitted` with nothing attached is not
   a claim anyone can review.
5. **Whoever submits cannot accept.** Execution and acceptance are separate
   authorities. This is ADR 0002 applied to production: the actor that did the
   work does not close it.
6. **Rejection, blocking and cancellation state a reason.** A rejection without
   a reason is a correction nobody can learn from.

### Graph rules live in the control plane

`ControlPlane.add_work_unit` requires every dependency, and the work package if
one is named, to exist already. A unit can only point at units recorded before
it, so the work graph is acyclic by construction; no cycle detection is needed
and none can be bypassed. `ready` is refused until every dependency is
`accepted`. Replay applies the same rules, so a log in which the submitter
accepts its own work does not reduce.

### What is deliberately not on the unit

Actual effort, cost and human touch are facts about an attempt, recorded by
whoever measured them. Putting them on the unit would make the unit's latest
value overwrite the history the economics depend on. They belong to a
production ledger that reads `work_unit.*` events, which is the next contract.

`acceptedBy` records who accepted, not whether they were entitled to. Which
roles may accept which capability on which project is an authority policy for
the deployment layer; the core guarantees only the separation.

## Consequences

- New events: `work_unit.created`, `work_unit.assigned`,
  `work_unit.transitioned`. Logs written by earlier builds replay unchanged; an
  earlier build refuses a log containing these events rather than reducing it
  into a state that omits them, which is how replay is meant to fail closed.
- `validate_semantics("work-unit.schema.json", ...)` enforces the cross-field
  invariants for producers in any language.
- Submitted work produces a `work_unit_review` task in the activity projection.
- `work.py` is held to the kernel coverage floor.
- `WorkPackage` is unchanged. Its own states (`evidence_claimed`, `verified`,
  `approved`) predate work units; reconciling the two lifecycles is left to a
  later ADR rather than changed silently here.

## Alternatives considered

**Extend `WorkPackage` with these fields.** Rejected: a package is the unit a
customer buys and a lead schedules; a work unit is what one executor performs
in one attempt. Merging them forces either packages small enough to be one
attempt or attempts large enough to be a package.

**Record actual effort on the unit.** Rejected for the reason above: the
economics need every attempt, and a field keeps only the last.

**Name agents rather than executor kinds.** Rejected: agents, models and
vendors change; the capability the work needs does not. SFC orchestrates work,
not agents.
