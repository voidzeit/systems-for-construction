"""Deterministic lifecycle rules for control-plane aggregates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any


class ObligationStatus(StrEnum):
    DISCOVERED = "discovered"
    CLASSIFIED = "classified"
    ACCEPTED = "accepted"
    ALLOCATED = "allocated"
    IN_PROGRESS = "in_progress"
    CLAIMED_SATISFIED = "claimed_satisfied"
    VERIFIED = "verified"
    APPROVED = "approved"


class WorkPackageStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    EVIDENCE_CLAIMED = "evidence_claimed"
    VERIFIED = "verified"
    APPROVED = "approved"
    CLOSED = "closed"


class ValueStatus(StrEnum):
    UNBUDGETED = "Unbudgeted"
    BUDGETED = "Budgeted"
    COMMITTED = "Committed"
    PLANNED = "Planned"
    EARNED = "Earned"
    CERTIFIED = "Certified"
    BILLED = "Billed"
    APPROVED_FOR_PAYMENT = "Approved for Payment"
    PAID = "Paid"
    COLLECTED = "Collected"


OBLIGATION_TRANSITIONS = {
    ObligationStatus.DISCOVERED: {ObligationStatus.CLASSIFIED},
    ObligationStatus.CLASSIFIED: {ObligationStatus.ACCEPTED},
    ObligationStatus.ACCEPTED: {ObligationStatus.ALLOCATED},
    ObligationStatus.ALLOCATED: {ObligationStatus.IN_PROGRESS},
    ObligationStatus.IN_PROGRESS: {ObligationStatus.CLAIMED_SATISFIED},
    ObligationStatus.CLAIMED_SATISFIED: {ObligationStatus.VERIFIED},
    ObligationStatus.VERIFIED: {ObligationStatus.APPROVED},
    ObligationStatus.APPROVED: set(),
}

WORK_PACKAGE_TRANSITIONS = {
    WorkPackageStatus.PLANNED: {WorkPackageStatus.IN_PROGRESS},
    WorkPackageStatus.IN_PROGRESS: {WorkPackageStatus.EVIDENCE_CLAIMED},
    WorkPackageStatus.EVIDENCE_CLAIMED: {WorkPackageStatus.VERIFIED},
    WorkPackageStatus.VERIFIED: {WorkPackageStatus.APPROVED},
    WorkPackageStatus.APPROVED: {WorkPackageStatus.CLOSED},
    WorkPackageStatus.CLOSED: set(),
}

VALUE_TRANSITIONS = {
    current: {next_status}
    for current, next_status in zip(ValueStatus, list(ValueStatus)[1:])
}
VALUE_TRANSITIONS[ValueStatus.COLLECTED] = set()


def transition(current, target, graph: dict) -> object:
    """Return the target state or reject a skipped/unauthorized transition."""
    if target not in graph.get(current, set()):
        raise ValueError(f"invalid transition: {current} -> {target}")
    return target


@dataclass(frozen=True)
class WorkPackage:
    work_package_id: str
    title: str
    obligation_ids: tuple[str, ...]
    status: WorkPackageStatus = WorkPackageStatus.PLANNED
    actor_id: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WorkPackage":
        return cls(
            work_package_id=value.get("workPackageId", ""),
            title=value.get("title", ""),
            obligation_ids=tuple(value.get("obligationIds", [])),
            status=WorkPackageStatus(value.get("status", "planned")),
            actor_id=value.get("actorId"),
            evidence_ids=tuple(value.get("evidenceIds", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workPackageId": self.work_package_id,
            "title": self.title,
            "obligationIds": list(self.obligation_ids),
            "actorId": self.actor_id,
            "status": self.status.value,
            "evidenceIds": list(self.evidence_ids),
        }

    def advance(self, target: WorkPackageStatus) -> "WorkPackage":
        transition(self.status, target, WORK_PACKAGE_TRANSITIONS)
        return replace(self, status=target)

