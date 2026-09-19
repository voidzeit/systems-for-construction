"""Portable Work Unit contract and deterministic lifecycle semantics."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any


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

    def advance(self, target: WorkUnitStatus, *, blocked_reason: str | None = None) -> "WorkUnit":
        if target not in WORK_UNIT_TRANSITIONS[self.state]:
            raise ValueError(f"invalid work-unit transition: {self.state} -> {target}")
        if target is WorkUnitStatus.BLOCKED and not blocked_reason:
            raise ValueError("blocked work unit requires blocked_reason")
        next_reason = blocked_reason if target is WorkUnitStatus.BLOCKED else None
        return replace(self, state=target, blocked_reason=next_reason)
