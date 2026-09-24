"""Portable Work Unit contract and deterministic lifecycle semantics.

A work package groups obligations. It does not say what has to be produced,
by which capability, from which inputs, or how anyone will know the result is
acceptable. A work unit does, and it is the aggregate the production loop
turns on:

    obligation -> work unit -> executor -> output -> QA -> review -> acceptance

This module owns the contract and the rules that hold inside one unit. Rules
that need more than one unit, or the history of one - a dependency must exist
and be accepted before its dependant is ready, the actor who submitted work
cannot accept it - belong to ``sfc.control_plane``, which holds the graph and
reduces the log. See ADR 0011 and ADR 0013.

The rules held here:

- Work in progress has an executor. A unit cannot start running unassigned,
  and the executor may change only before an attempt starts or after it has
  been sent back for correction.
- A block says why, and leaving it clears the reason.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import re
from typing import Any, Iterable


class WorkUnitStatus(StrEnum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    RETRY = "retry"
    CANCELLED = "cancelled"
    MACHINE_QA = "machine_qa"
    HUMAN_REVIEW = "human_review"
    CORRECTION = "correction"
    ESCALATED = "escalated"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    LEARNED = "learned"


WORK_UNIT_TRANSITIONS: dict[WorkUnitStatus, set[WorkUnitStatus]] = {
    WorkUnitStatus.CREATED: {WorkUnitStatus.READY, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.READY: {WorkUnitStatus.RUNNING, WorkUnitStatus.BLOCKED, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.RUNNING: {WorkUnitStatus.MACHINE_QA, WorkUnitStatus.BLOCKED, WorkUnitStatus.RETRY, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.BLOCKED: {WorkUnitStatus.READY, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.RETRY: {WorkUnitStatus.RUNNING, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.MACHINE_QA: {WorkUnitStatus.HUMAN_REVIEW, WorkUnitStatus.CORRECTION, WorkUnitStatus.ESCALATED},
    WorkUnitStatus.HUMAN_REVIEW: {WorkUnitStatus.ACCEPTED, WorkUnitStatus.CORRECTION, WorkUnitStatus.ESCALATED},
    WorkUnitStatus.CORRECTION: {WorkUnitStatus.READY, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.ESCALATED: {WorkUnitStatus.HUMAN_REVIEW, WorkUnitStatus.READY, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.ACCEPTED: {WorkUnitStatus.DELIVERED},
    WorkUnitStatus.DELIVERED: {WorkUnitStatus.LEARNED},
    WorkUnitStatus.CANCELLED: set(),
    WorkUnitStatus.LEARNED: set(),
}

#: States the executor may still be (re)named in. Once an attempt runs, it
#: belongs to whoever started it until it is sent back for correction.
ASSIGNABLE = frozenset({WorkUnitStatus.CREATED, WorkUnitStatus.READY, WorkUnitStatus.BLOCKED, WorkUnitStatus.CORRECTION})

#: States that are only reachable through ``running``, so the unit has an executor.
EXECUTED = frozenset(set(WorkUnitStatus) - {WorkUnitStatus.CREATED, WorkUnitStatus.READY, WorkUnitStatus.BLOCKED, WorkUnitStatus.CANCELLED})

#: States in which the unit holds an accepted output. A dependant may start
#: only once every dependency is in one of them.
ACCEPTED_STATES = frozenset({WorkUnitStatus.ACCEPTED, WorkUnitStatus.DELIVERED, WorkUnitStatus.LEARNED})

#: Transitions whose event must say why. A correction without a reason cannot
#: be learned from, and an escalation or cancellation without one cannot be
#: acted on by anyone else. ``blocked`` carries its reason on the unit itself.
REASON_REQUIRED = frozenset({WorkUnitStatus.CORRECTION, WorkUnitStatus.ESCALATED, WorkUnitStatus.CANCELLED})

CAPABILITY_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")


class WorkUnitError(ValueError):
    """Raised when a work unit transition or definition breaks the contract."""


@dataclass(frozen=True)
class WorkUnit:
    work_unit_id: str
    project_id: str
    work_package_id: str
    capability_id: str
    scope: str
    discipline: str | None = None
    location: str | None = None
    requirement_ids: tuple[str, ...] = ()
    input_ids: tuple[str, ...] = ()
    dependency_ids: tuple[str, ...] = ()
    executor_id: str | None = None
    expected_output: str | None = None
    acceptance_criteria: tuple[str, ...] = ()
    qa_criteria: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    #: None means not estimated or not measured. It is never read as zero.
    estimated_effort_hours: float | None = None
    actual_effort_hours: float | None = None
    compute_cost: float | None = None
    cost: float | None = None
    state: WorkUnitStatus = WorkUnitStatus.CREATED
    blocked_reason: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WorkUnit":
        return cls(
            work_unit_id=value.get("workUnitId", ""),
            project_id=value.get("projectId", ""),
            work_package_id=value.get("workPackageId", ""),
            capability_id=value.get("capabilityId", ""),
            scope=value.get("scope", ""),
            discipline=value.get("discipline"),
            location=value.get("location"),
            requirement_ids=tuple(value.get("requirementIds", [])),
            input_ids=tuple(value.get("inputIds", [])),
            dependency_ids=tuple(value.get("dependencyIds", [])),
            executor_id=value.get("executorId"),
            expected_output=value.get("expectedOutput"),
            acceptance_criteria=tuple(value.get("acceptanceCriteria", [])),
            qa_criteria=tuple(value.get("qaCriteria", [])),
            evidence_ids=tuple(value.get("evidenceIds", [])),
            estimated_effort_hours=value.get("estimatedEffortHours"),
            actual_effort_hours=value.get("actualEffortHours"),
            compute_cost=value.get("computeCost"),
            cost=value.get("cost"),
            state=WorkUnitStatus(value.get("state", "created")),
            blocked_reason=value.get("blockedReason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workUnitId": self.work_unit_id,
            "projectId": self.project_id,
            "workPackageId": self.work_package_id,
            "capabilityId": self.capability_id,
            "scope": self.scope,
            "discipline": self.discipline,
            "location": self.location,
            "requirementIds": list(self.requirement_ids),
            "inputIds": list(self.input_ids),
            "dependencyIds": list(self.dependency_ids),
            "executorId": self.executor_id,
            "expectedOutput": self.expected_output,
            "acceptanceCriteria": list(self.acceptance_criteria),
            "qaCriteria": list(self.qa_criteria),
            "evidenceIds": list(self.evidence_ids),
            "estimatedEffortHours": self.estimated_effort_hours,
            "actualEffortHours": self.actual_effort_hours,
            "computeCost": self.compute_cost,
            "cost": self.cost,
            "state": self.state.value,
            "blockedReason": self.blocked_reason,
        }

    def assign(self, executor_id: str) -> "WorkUnit":
        """Name the executor. Only while no attempt is running or under review."""
        if self.state not in ASSIGNABLE:
            raise WorkUnitError(f"cannot reassign a work unit in state {self.state.value}")
        if not executor_id:
            raise WorkUnitError("an executor must be identified")
        return replace(self, executor_id=executor_id)

    def advance(self, target: WorkUnitStatus, *, blocked_reason: str | None = None) -> "WorkUnit":
        if target not in WORK_UNIT_TRANSITIONS[self.state]:
            raise WorkUnitError(f"invalid work-unit transition: {self.state} -> {target}")
        if target is WorkUnitStatus.BLOCKED and not blocked_reason:
            raise WorkUnitError("blocked work unit requires blocked_reason")
        if target is WorkUnitStatus.RUNNING and not self.executor_id:
            raise WorkUnitError("work cannot start without an assigned executor")
        next_reason = blocked_reason if target is WorkUnitStatus.BLOCKED else None
        return replace(self, state=target, blocked_reason=next_reason)


def work_unit_violations(document: dict[str, Any]) -> Iterable[str]:
    """Cross-field invariants of one work unit document.

    Stdlib-only and dictionary-based, so it applies to a unit this runtime did
    not produce. Graph and history rules - dependencies exist and are accepted
    before their dependants start, the submitter does not accept - need every
    unit and the log, and live in the control plane.
    """
    unit_id = document.get("workUnitId")
    capability = document.get("capabilityId") or ""
    if not CAPABILITY_PATTERN.match(capability):
        yield f"capabilityId {capability!r} must be a dotted identifier such as electrical.route.feeder"

    if unit_id in (document.get("dependencyIds") or []):
        yield "a work unit cannot depend on itself"

    state = document.get("state")
    if state in {item.value for item in EXECUTED} and not document.get("executorId"):
        yield f"a work unit in state {state} must have an assigned executor"

    if state != WorkUnitStatus.BLOCKED.value and document.get("blockedReason"):
        yield f"a work unit in state {state} cannot carry a blockedReason"
