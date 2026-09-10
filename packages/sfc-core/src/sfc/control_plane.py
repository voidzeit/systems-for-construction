"""Local application service for governed SFC control-plane workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .events import Event, EventLog
from .governance import Review, ReviewDecision, ValueRecord, current_review
from .lifecycle import ObligationStatus, WorkPackage, WorkPackageStatus, transition, OBLIGATION_TRANSITIONS


@dataclass
class ControlPlane:
    """In-memory reference service with an append-only event boundary."""

    event_log: EventLog | None = None
    obligation_states: dict[str, ObligationStatus] = field(default_factory=dict)
    work_packages: dict[str, WorkPackage] = field(default_factory=dict)
    reviews: list[Review] = field(default_factory=list)
    values: dict[str, ValueRecord] = field(default_factory=dict)

    def register_obligation(self, obligation_id: str) -> ObligationStatus:
        if obligation_id in self.obligation_states:
            raise ValueError(f"obligation already exists: {obligation_id}")
        self.obligation_states[obligation_id] = ObligationStatus.DISCOVERED
        self._emit("obligation.discovered", obligation_id, {"status": ObligationStatus.DISCOVERED.value})
        return self.obligation_states[obligation_id]

    def advance_obligation(self, obligation_id: str, target: ObligationStatus, actor_id: str) -> ObligationStatus:
        current = self.obligation_states[obligation_id]
        transition(current, target, OBLIGATION_TRANSITIONS)
        self.obligation_states[obligation_id] = target
        self._emit("obligation.transitioned", obligation_id, {"from": current.value, "to": target.value}, actor_id)
        return target

    def add_work_package(self, package: WorkPackage) -> None:
        if package.work_package_id in self.work_packages:
            raise ValueError(f"work package already exists: {package.work_package_id}")
        self.work_packages[package.work_package_id] = package
        self._emit("work_package.created", package.work_package_id, package.__dict__)

    def advance_work_package(self, work_package_id: str, target: WorkPackageStatus, actor_id: str) -> WorkPackage:
        package = self.work_packages[work_package_id]
        updated = package.advance(target)
        self.work_packages[work_package_id] = updated
        self._emit("work_package.transitioned", work_package_id, {"from": package.status.value, "to": target.value}, actor_id)
        return updated

    def add_review(self, review: Review) -> Review:
        if review.decision is ReviewDecision.REVOKED and not review.supersedes_review_id:
            raise ValueError("revocation must identify the review it supersedes")
        self.reviews.append(review)
        self._emit("review.added", review.target_id, {"reviewId": review.review_id, "decision": review.decision.value}, review.reviewer_id)
        return review

    def current_review(self, target_id: str) -> Review | None:
        return current_review(self.reviews, target_id)

    def add_value(self, value: ValueRecord) -> None:
        if value.value_id in self.values:
            raise ValueError(f"value already exists: {value.value_id}")
        self.values[value.value_id] = value
        self._emit("value.created", value.value_id, {"status": value.status.value})

    def advance_value(self, value_id: str, target, *, evidence_ids: tuple[str, ...] = (), actor_id: str | None = None) -> ValueRecord:
        value = self.values[value_id]
        updated = value.advance(target, evidence_ids=evidence_ids)
        self.values[value_id] = updated
        self._emit("value.transitioned", value_id, {"from": value.status.value, "to": target.value, "evidenceIds": list(evidence_ids)}, actor_id)
        return updated

    def _emit(self, event_type: str, aggregate_id: str, payload: dict[str, Any], actor_id: str | None = None) -> None:
        if self.event_log:
            self.event_log.append(Event(event_type, aggregate_id, payload, actor_id=actor_id))
