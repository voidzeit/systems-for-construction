"""The Work Unit: the smallest piece of production work SFC can govern.

A work package groups obligations. It does not say what has to be produced,
by whom, from which inputs, or how anyone will know the result is acceptable.
A work unit does, and it is the aggregate the production loop turns on:

    obligation -> work unit -> executor -> output -> review -> acceptance

This module owns the contract and the rules that do not depend on anything
outside one unit. Rules across units - a dependency must exist and be accepted
before its dependant is ready - belong to ``sfc.control_plane``, which holds
the graph. What a unit *cost* is not recorded here: effort actually spent is a
fact about an attempt, and belongs to a production ledger that reads this
unit's events rather than to a field on it. See ADR 0011.

Three rules make the lifecycle more than a list of states:

- Work in progress has an executor. A unit cannot start unassigned, and the
  executor must be of a kind its policy allows.
- A claim of completion names what was produced. Submission requires output
  identifiers; ``submitted`` with nothing attached is not a claim anyone can
  review.
- Whoever submits cannot accept. Execution and acceptance are separate
  authorities, so the same actor can never close its own work.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
import re
from typing import Any, Iterable

from .quantities import Dimension, Quantity, dimension_of


class WorkUnitStatus(StrEnum):
    PLANNED = "planned"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ExecutorKind(StrEnum):
    """What performs the work. A capability is stable; its executor is not."""

    HUMAN = "human"
    CODE = "code"
    SOLVER = "solver"
    LLM = "llm"
    REVIT = "revit"
    EXTERNAL = "external"


class AutonomyClass(StrEnum):
    MANUAL = "manual"
    ASSISTED = "assisted"
    SUPERVISED = "supervised"
    AUTOMATED = "automated"


class RiskClass(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


WORK_UNIT_TRANSITIONS = {
    WorkUnitStatus.PLANNED: {WorkUnitStatus.READY, WorkUnitStatus.BLOCKED, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.READY: {WorkUnitStatus.IN_PROGRESS, WorkUnitStatus.BLOCKED, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.IN_PROGRESS: {WorkUnitStatus.SUBMITTED, WorkUnitStatus.BLOCKED, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.BLOCKED: {WorkUnitStatus.READY, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.SUBMITTED: {WorkUnitStatus.ACCEPTED, WorkUnitStatus.REJECTED},
    WorkUnitStatus.REJECTED: {WorkUnitStatus.IN_PROGRESS, WorkUnitStatus.CANCELLED},
    WorkUnitStatus.ACCEPTED: set(),
    WorkUnitStatus.CANCELLED: set(),
}

#: Transitions that must say why. A rejection without a reason cannot be
#: learned from, and a block without one cannot be cleared by anyone else.
REASON_REQUIRED = frozenset({WorkUnitStatus.BLOCKED, WorkUnitStatus.REJECTED, WorkUnitStatus.CANCELLED})

#: States in which the unit has started, so it must have an executor.
STARTED = frozenset({WorkUnitStatus.IN_PROGRESS, WorkUnitStatus.SUBMITTED, WorkUnitStatus.ACCEPTED})

#: States in which the executor may still change. Once work has started, the
#: attempt belongs to whoever started it.
ASSIGNABLE = frozenset({WorkUnitStatus.PLANNED, WorkUnitStatus.READY, WorkUnitStatus.BLOCKED, WorkUnitStatus.REJECTED})

#: States that claim an output exists.
CLAIMED = frozenset({WorkUnitStatus.SUBMITTED, WorkUnitStatus.ACCEPTED})

CAPABILITY_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")


class WorkUnitError(ValueError):
    """Raised when a work unit transition or definition breaks the contract."""


@dataclass(frozen=True)
class InputRef:
    """A source the work consumes, pinned to the revision it was planned on."""

    source_id: str
    revision: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "InputRef":
        return cls(value.get("sourceId", ""), value.get("revision"))

    def to_dict(self) -> dict[str, Any]:
        return {"sourceId": self.source_id, "revision": self.revision}


@dataclass(frozen=True)
class ExpectedOutput:
    kind: str
    description: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExpectedOutput":
        return cls(value.get("kind", ""), value.get("description"))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "description": self.description}


@dataclass(frozen=True)
class AcceptanceCriterion:
    criterion_id: str
    statement: str
    obligation_id: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AcceptanceCriterion":
        return cls(value.get("criterionId", ""), value.get("statement", ""), value.get("obligationId"))

    def to_dict(self) -> dict[str, Any]:
        return {"criterionId": self.criterion_id, "statement": self.statement, "obligationId": self.obligation_id}


@dataclass(frozen=True)
class ExecutorPolicy:
    allowed_kinds: tuple[ExecutorKind, ...] = (ExecutorKind.HUMAN,)
    autonomy: AutonomyClass = AutonomyClass.MANUAL

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExecutorPolicy":
        return cls(
            tuple(ExecutorKind(kind) for kind in value.get("allowedKinds", ["human"])),
            AutonomyClass(value.get("autonomy", "manual")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"allowedKinds": [kind.value for kind in self.allowed_kinds], "autonomy": self.autonomy.value}


@dataclass(frozen=True)
class Assignee:
    kind: ExecutorKind
    executor_id: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Assignee":
        return cls(ExecutorKind(value.get("kind", "")), value.get("executorId", ""))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "executorId": self.executor_id}


def _effort_from_dict(value: Any) -> Quantity | None:
    if value is None:
        return None
    return Quantity(float(value["value"]), value.get("unit"))


def _effort_to_dict(value: Quantity | None) -> dict[str, Any] | None:
    return None if value is None else {"value": value.value, "unit": value.unit}


@dataclass(frozen=True)
class WorkUnit:
    work_unit_id: str
    title: str
    capability: str
    work_package_id: str | None = None
    scope: str | None = None
    discipline: str | None = None
    location: str | None = None
    inputs: tuple[InputRef, ...] = ()
    obligation_ids: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    executor_policy: ExecutorPolicy = field(default_factory=ExecutorPolicy)
    expected_outputs: tuple[ExpectedOutput, ...] = ()
    acceptance_criteria: tuple[AcceptanceCriterion, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    #: None means not estimated. It is never read as zero.
    estimated_effort: Quantity | None = None
    risk_class: RiskClass | None = None
    status: WorkUnitStatus = WorkUnitStatus.PLANNED
    attempt: int = 0
    assignee: Assignee | None = None
    output_ids: tuple[str, ...] = ()
    submitted_by: str | None = None
    accepted_by: str | None = None
    status_reason: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WorkUnit":
        assignee = value.get("assignee")
        risk = value.get("riskClass")
        return cls(
            work_unit_id=value.get("workUnitId", ""),
            title=value.get("title", ""),
            capability=value.get("capability", ""),
            work_package_id=value.get("workPackageId"),
            scope=value.get("scope"),
            discipline=value.get("discipline"),
            location=value.get("location"),
            inputs=tuple(InputRef.from_dict(item) for item in value.get("inputs", [])),
            obligation_ids=tuple(value.get("obligationIds", [])),
            depends_on=tuple(value.get("dependsOn", [])),
            executor_policy=ExecutorPolicy.from_dict(value.get("executorPolicy", {})),
            expected_outputs=tuple(ExpectedOutput.from_dict(item) for item in value.get("expectedOutputs", [])),
            acceptance_criteria=tuple(AcceptanceCriterion.from_dict(item) for item in value.get("acceptanceCriteria", [])),
            evidence_requirements=tuple(value.get("evidenceRequirements", [])),
            estimated_effort=_effort_from_dict(value.get("estimatedEffort")),
            risk_class=None if risk is None else RiskClass(risk),
            status=WorkUnitStatus(value.get("status", "planned")),
            attempt=int(value.get("attempt", 0)),
            assignee=None if assignee is None else Assignee.from_dict(assignee),
            output_ids=tuple(value.get("outputIds", [])),
            submitted_by=value.get("submittedBy"),
            accepted_by=value.get("acceptedBy"),
            status_reason=value.get("statusReason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workUnitId": self.work_unit_id,
            "title": self.title,
            "capability": self.capability,
            "workPackageId": self.work_package_id,
            "scope": self.scope,
            "discipline": self.discipline,
            "location": self.location,
            "inputs": [item.to_dict() for item in self.inputs],
            "obligationIds": list(self.obligation_ids),
            "dependsOn": list(self.depends_on),
            "executorPolicy": self.executor_policy.to_dict(),
            "expectedOutputs": [item.to_dict() for item in self.expected_outputs],
            "acceptanceCriteria": [item.to_dict() for item in self.acceptance_criteria],
            "evidenceRequirements": list(self.evidence_requirements),
            "estimatedEffort": _effort_to_dict(self.estimated_effort),
            "riskClass": None if self.risk_class is None else self.risk_class.value,
            "status": self.status.value,
            "attempt": self.attempt,
            "assignee": None if self.assignee is None else self.assignee.to_dict(),
            "outputIds": list(self.output_ids),
            "submittedBy": self.submitted_by,
            "acceptedBy": self.accepted_by,
            "statusReason": self.status_reason,
        }

    def assign(self, kind: ExecutorKind, executor_id: str) -> "WorkUnit":
        """Name the executor. Only before work starts, and only an allowed kind."""
        if self.status not in ASSIGNABLE:
            raise WorkUnitError(f"cannot reassign a work unit in status {self.status.value}")
        if not executor_id:
            raise WorkUnitError("an executor must be identified")
        if kind not in self.executor_policy.allowed_kinds:
            allowed = ", ".join(item.value for item in self.executor_policy.allowed_kinds)
            raise WorkUnitError(f"executor kind {kind.value} is not allowed for {self.work_unit_id} (allowed: {allowed})")
        return replace(self, assignee=Assignee(kind, executor_id))

    def advance(
        self,
        target: WorkUnitStatus,
        actor_id: str,
        *,
        output_ids: Iterable[str] = (),
        reason: str | None = None,
    ) -> "WorkUnit":
        """Apply one governed transition, or refuse it."""
        if target not in WORK_UNIT_TRANSITIONS[self.status]:
            raise WorkUnitError(f"invalid transition: {self.status.value} -> {target.value}")
        if not actor_id:
            raise WorkUnitError("every work unit transition must identify its actor")
        if target in REASON_REQUIRED and not reason:
            raise WorkUnitError(f"moving to {target.value} requires a reason")
        outputs = tuple(output_ids)
        changes: dict[str, Any] = {"status": target, "status_reason": reason}

        if target is WorkUnitStatus.IN_PROGRESS:
            if self.assignee is None:
                raise WorkUnitError("work cannot start without an assigned executor")
            # Every entry into execution is a new attempt. A reworked unit
            # starts clean: the rejected outputs stay in the event log, not on
            # the unit, so the next submission cannot inherit them.
            changes.update(attempt=self.attempt + 1, output_ids=(), submitted_by=None)
        elif target is WorkUnitStatus.SUBMITTED:
            if not outputs:
                raise WorkUnitError("a submission must name the outputs it claims to have produced")
            if len(set(outputs)) != len(outputs):
                raise WorkUnitError("submitted output identifiers must be unique")
            changes.update(output_ids=outputs, submitted_by=actor_id)
        elif target is WorkUnitStatus.ACCEPTED:
            if actor_id == self.submitted_by:
                raise WorkUnitError("the actor who submitted a work unit cannot accept it")
            changes.update(accepted_by=actor_id)

        if outputs and target is not WorkUnitStatus.SUBMITTED:
            raise WorkUnitError("outputs are recorded only on submission")
        return replace(self, **changes)


def work_unit_violations(document: dict[str, Any]) -> Iterable[str]:
    """Cross-field invariants of one work unit document.

    Stdlib-only and dictionary-based, so it applies to a unit this runtime did
    not produce. Graph rules - dependencies exist, are acyclic and are accepted
    before their dependants start - need every unit and live in the control
    plane.
    """
    unit_id = document.get("workUnitId")
    capability = document.get("capability") or ""
    if not CAPABILITY_PATTERN.match(capability):
        yield f"capability {capability!r} must be a dotted identifier such as electrical.route.feeder"

    depends_on = list(document.get("dependsOn") or [])
    if unit_id in depends_on:
        yield "a work unit cannot depend on itself"
    if len(set(depends_on)) != len(depends_on):
        yield "dependsOn repeats a work unit"

    criteria = [item.get("criterionId") for item in document.get("acceptanceCriteria") or []]
    if len(set(criteria)) != len(criteria):
        yield "acceptance criterion identifiers must be unique"

    effort = document.get("estimatedEffort")
    if effort is not None:
        try:
            if dimension_of(effort.get("unit")) is not Dimension.TIME:
                yield "estimatedEffort must be expressed in a unit of time"
        except (ValueError, TypeError):
            yield f"estimatedEffort unit {effort.get('unit')!r} is not a known unit"
        if isinstance(effort.get("value"), (int, float)) and effort["value"] < 0:
            yield "estimatedEffort cannot be negative"

    status = document.get("status")
    assignee = document.get("assignee")
    allowed = (document.get("executorPolicy") or {}).get("allowedKinds") or []
    if assignee is not None and assignee.get("kind") not in allowed:
        yield f"assignee kind {assignee.get('kind')!r} is not allowed by the executor policy"
    if status in {item.value for item in STARTED} and assignee is None:
        yield f"a work unit in status {status} must have an assigned executor"
    if status in {item.value for item in STARTED} and (document.get("attempt") or 0) < 1:
        yield f"a work unit in status {status} must record at least one attempt"

    outputs = list(document.get("outputIds") or [])
    if status in {item.value for item in CLAIMED}:
        if not outputs:
            yield f"a work unit in status {status} must name its outputs"
        if not document.get("submittedBy"):
            yield f"a work unit in status {status} must record who submitted it"
    elif outputs and status != WorkUnitStatus.REJECTED.value:
        # A rejected unit keeps the outputs that were rejected, so the review
        # names what it refused. Any other state carries none.
        yield f"a work unit in status {status} carries outputs it has not submitted"
    if len(set(outputs)) != len(outputs):
        yield "outputIds repeats an output"

    accepted_by = document.get("acceptedBy")
    if status == WorkUnitStatus.ACCEPTED.value:
        if not accepted_by:
            yield "an accepted work unit must record who accepted it"
        elif accepted_by == document.get("submittedBy"):
            yield "a work unit cannot be accepted by the actor who submitted it"
    elif accepted_by:
        yield f"a work unit in status {status} cannot record an acceptance"

    if status in {item.value for item in REASON_REQUIRED} and not document.get("statusReason"):
        yield f"a work unit in status {status} must state its reason"
