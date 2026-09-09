# SFC status vocabulary

## Obligation

`discovered → classified → accepted → allocated → in_progress → claimed_satisfied → verified → approved`

## Work package

`planned → in_progress → evidence_claimed → verified → approved → closed`

## Value

`Unbudgeted → Budgeted → Committed → Planned → Earned → Certified → Billed → Approved for Payment → Paid → Collected`

Transitions are explicit and sequential. A connector or agent may propose a
transition, but an application service must enforce the deterministic graph
and record the event.

