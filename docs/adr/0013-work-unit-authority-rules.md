# ADR 0013: A work unit names its executor, and whoever submits cannot accept

## Status

Accepted.

## Context

ADR 0011 made the Work Unit the durable production primitive and fixed its
portable fields and lifecycle. It left the lifecycle permissive: any caller
could move a unit from `human_review` to `accepted`, a unit could start
`running` with no executor, a submission did not have to say what it produced,
and nothing ordered units against their `dependencyIds`. The same actor could
therefore produce work and close it, which is the authority boundary ADR 0002
draws for agents, left open for production.

A parallel draft (an earlier, unpublished ADR 0011, "the work unit is the unit
of production") had specified these rules against a different field set. This
ADR keeps the published contract of ADR 0011 unchanged and adopts the rules
from that draft that can be enforced without changing the schema.

## Decision

### Rules inside one unit (`sfc.work`)

1. **Work in progress has an executor.** `running` is refused while
   `executorId` is empty. The executor may be (re)named only in `created`,
   `ready`, `blocked` and `correction`: once an attempt runs, it belongs to
   whoever started it until it is sent back.
2. **A block says why**, and leaving it clears the reason (unchanged from
   ADR 0011).

`validate_semantics("work-unit.schema.json", ...)` checks the document form of
these rules, plus a dotted `capabilityId` and no self-dependency, for producers
in any language.

### Rules that need the graph or the log (`sfc.control_plane`)

3. **Every transition and assignment names its actor.**
4. **The graph is acyclic by construction.** The work package and every
   dependency must exist before a unit is created, so a unit can only point at
   units recorded before it. A unit becomes `ready` only when every dependency
   is `accepted`, `delivered` or `learned`.
5. **A submission names its outputs.** `running -> machine_qa` requires unique
   `outputIds`, recorded in the event. No other transition records outputs.
6. **Whoever executes or submits cannot accept.** `human_review -> accepted`
   is refused when the actor is the unit's executor or the actor who submitted
   the current attempt. The submitter is read from the log, not stored on the
   unit, so replay refuses a self-accepted log.
7. **Correction, escalation and cancellation state a reason** in the event. A
   correction without a reason is one nobody can learn from.

New event: `work_unit.assigned`. Replay applies the same rules as live
execution, so a log that breaks any of them does not reduce.

Submitted work reaching `human_review`, and escalated work, become tasks in the
activity projection (`work_unit_review`, `work_unit_escalation`).

## Not adopted from the draft

These would change the published schema, and are left for a later ADR rather
than changed silently:

- **Pinned input revisions** (`inputs: [{sourceId, revision}]`). `inputIds`
  cannot tell work planned on one drawing revision from work delivered against
  another.
- **Executor kinds and an executor policy** (human, code, solver, model, host
  runtime, external; allowed kinds and autonomy per unit). ADR 0012 places the
  autonomy ceiling and risk class on the plugin capability instead; whether a
  unit may further restrict them is open.
- **An attempt counter and `submittedBy` / `acceptedBy` on the unit.** The log
  carries them today.
- **Structured acceptance criteria** with identifiers traceable to obligations.

## Open

The draft argued that actual effort and cost are facts about an attempt and
belong to a production ledger that reads `work_unit.*` events, because a field
on the unit keeps only the last value. ADR 0011 publishes `actualEffortHours`,
`computeCost` and `cost` on the unit. Which one is authoritative for production
economics needs a decision before any producer relies on either.
