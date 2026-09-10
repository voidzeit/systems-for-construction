"""Local application service for governed SFC control-plane workflows.

This is reference semantics, not a durable service. State lives in memory and
is gone when the process ends; the event log is the only thing that persists.
That is a deliberate boundary - SFC Core answers *what a valid control-plane
transition is*, and a deployment layer answers *who may execute it at scale, and
where the state lives*.

What the core does owe such a deployment is a log it can be rebuilt from, so
``from_events`` reduces the log back into derived state:

    append-only log  ->  reducer  ->  derived state

Replay applies the same domain rules as live execution, so a log containing an
invalid sequence fails to replay rather than reconstructing a state the rules
forbid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .events import Event, EventLog
from .governance import Review, ReviewDecision, ValueRecord, current_review
from .lifecycle import ObligationStatus, ValueStatus, WorkPackage, WorkPackageStatus, transition, OBLIGATION_TRANSITIONS


class ReplayError(ValueError):
    """Raised when an event log cannot be reduced into a valid state."""


@dataclass
class ControlPlane:
    """In-memory reference service with an append-only event boundary.

    Not durable. See the module docstring, and ``from_events`` to rebuild.
    """

    event_log: EventLog | None = None
    obligation_states: dict[str, ObligationStatus] = field(default_factory=dict)
    work_packages: dict[str, WorkPackage] = field(default_factory=dict)
    reviews: list[Review] = field(default_factory=list)
    values: dict[str, ValueRecord] = field(default_factory=dict)
    #: Event types the reducer does not account for. Recorded rather than
    #: dropped, so a log carrying events from another aggregate is visible.
    unapplied_events: list[dict[str, Any]] = field(default_factory=list)

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
        self._emit("work_package.created", package.work_package_id, package.to_dict())

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
        self._emit("review.added", review.target_id, review.to_dict(), review.reviewer_id)
        return review

    def current_review(self, target_id: str) -> Review | None:
        return current_review(self.reviews, target_id)

    def add_value(self, value: ValueRecord) -> None:
        if value.value_id in self.values:
            raise ValueError(f"value already exists: {value.value_id}")
        self.values[value.value_id] = value
        self._emit("value.created", value.value_id, value.to_dict())

    def advance_value(self, value_id: str, target, *, evidence_ids: tuple[str, ...] = (), actor_id: str | None = None) -> ValueRecord:
        value = self.values[value_id]
        updated = value.advance(target, evidence_ids=evidence_ids)
        self.values[value_id] = updated
        self._emit("value.transitioned", value_id, {"from": value.status.value, "to": target.value, "evidenceIds": list(evidence_ids)}, actor_id)
        return updated

    def _emit(self, event_type: str, aggregate_id: str, payload: dict[str, Any], actor_id: str | None = None) -> None:
        if self.event_log:
            self.event_log.append(Event(event_type, aggregate_id, payload, actor_id=actor_id))

    @classmethod
    def from_events(cls, events: Iterable[dict[str, Any]], *, event_log: EventLog | None = None) -> "ControlPlane":
        """Rebuild derived state by reducing the append-only log.

        The replayed plane is built with no log attached, so replay never
        re-emits what it is reading. ``event_log`` is attached to the result for
        subsequent live use.
        """
        plane = cls()
        for event in events:
            try:
                plane._apply(event)
            except (KeyError, ValueError) as error:
                raise ReplayError(
                    f"cannot replay {event.get('eventType')!r} for {event.get('aggregateId')!r}: {error}"
                ) from error
        plane.event_log = event_log
        return plane

    def _apply(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("eventType", ""))
        aggregate_id = str(event.get("aggregateId", ""))
        payload = event.get("payload", {}) or {}
        actor_id = event.get("actorId")
        if event_type == "obligation.discovered":
            self.register_obligation(aggregate_id)
        elif event_type == "obligation.transitioned":
            self.advance_obligation(aggregate_id, ObligationStatus(payload["to"]), actor_id or "")
        elif event_type == "work_package.created":
            self.add_work_package(WorkPackage.from_dict(payload))
        elif event_type == "work_package.transitioned":
            self.advance_work_package(aggregate_id, WorkPackageStatus(payload["to"]), actor_id or "")
        elif event_type == "review.added":
            self.add_review(Review.from_dict(payload))
        elif event_type == "value.created":
            self.add_value(ValueRecord.from_dict(payload))
        elif event_type == "value.transitioned":
            self.advance_value(
                aggregate_id,
                ValueStatus(payload["to"]),
                evidence_ids=tuple(payload.get("evidenceIds", [])),
                actor_id=actor_id,
            )
        else:
            self.unapplied_events.append(event)

    def replay_matches(self, events: Iterable[dict[str, Any]]) -> bool:
        """Whether reducing the log reproduces this plane's derived state."""
        return self.state() == ControlPlane.from_events(events).state()

    def state(self) -> dict[str, Any]:
        """The derived state, in the portable shape, for comparison and export."""
        return {
            "obligations": {key: value.value for key, value in sorted(self.obligation_states.items())},
            "workPackages": {key: value.to_dict() for key, value in sorted(self.work_packages.items())},
            "reviews": [review.to_dict() for review in self.reviews],
            "values": {key: value.to_dict() for key, value in sorted(self.values.items())},
        }
