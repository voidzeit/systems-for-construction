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

from .events import CONTROL_PLANE_EVENT_TYPES, Event, EventLog, ReplayError, owns_event
from .governance import Review, ReviewDecision, ValueRecord, current_review
from .lifecycle import ObligationStatus, ValueStatus, WorkPackage, WorkPackageStatus, transition, OBLIGATION_TRANSITIONS
from .work import ACCEPTED_STATES, REASON_REQUIRED, WorkUnit, WorkUnitError, WorkUnitStatus, work_unit_violations

__all__ = ["ControlPlane", "ReplayError"]


@dataclass
class ControlPlane:
    """In-memory reference service with an append-only event boundary.

    Not durable. See the module docstring, and ``from_events`` to rebuild.
    """

    event_log: EventLog | None = None
    obligation_states: dict[str, ObligationStatus] = field(default_factory=dict)
    work_packages: dict[str, WorkPackage] = field(default_factory=dict)
    work_units: dict[str, WorkUnit] = field(default_factory=dict)
    #: Who submitted each unit's current attempt, read from the log rather than
    #: stored on the unit, so the portable contract stays free of authority
    #: bookkeeping while replay still refuses a self-accepted unit.
    work_unit_submitters: dict[str, str] = field(default_factory=dict)
    reviews: list[Review] = field(default_factory=list)
    values: dict[str, ValueRecord] = field(default_factory=dict)
    #: Events another projection owns. Recorded rather than dropped, so a log
    #: carrying an evidence room's history is visible here without being read
    #: as control-plane state. An event type no projection owns is refused
    #: outright; see ``sfc.events.owns_event``.
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

    def add_work_unit(self, work_unit: WorkUnit) -> None:
        """Plan a work unit. Its package and dependencies must already exist.

        Requiring every dependency to exist at creation makes the work graph
        acyclic by construction: a unit can only point at units recorded before
        it, so no sequence of creations can close a loop.
        """
        if work_unit.work_unit_id in self.work_units:
            raise WorkUnitError(f"work unit already exists: {work_unit.work_unit_id}")
        if work_unit.state is not WorkUnitStatus.CREATED:
            raise WorkUnitError("a work unit enters the plane as created")
        if work_unit.work_package_id not in self.work_packages:
            raise WorkUnitError(f"unknown work package: {work_unit.work_package_id}")
        missing = [dependency for dependency in work_unit.dependency_ids if dependency not in self.work_units]
        if missing:
            raise WorkUnitError(f"{work_unit.work_unit_id} depends on unplanned work units: {', '.join(missing)}")
        violations = tuple(work_unit_violations(work_unit.to_dict()))
        if violations:
            raise WorkUnitError("; ".join(violations))
        self.work_units[work_unit.work_unit_id] = work_unit
        self._emit("work_unit.created", work_unit.work_unit_id, work_unit.to_dict())

    def assign_work_unit(self, work_unit_id: str, executor_id: str, actor_id: str) -> WorkUnit:
        if not actor_id:
            raise WorkUnitError("every work unit assignment must identify its actor")
        work_unit = self.work_units[work_unit_id]
        updated = work_unit.assign(executor_id)
        self.work_units[work_unit_id] = updated
        self._emit("work_unit.assigned", work_unit_id, {"executorId": executor_id}, actor_id)
        return updated

    def advance_work_unit(
        self,
        work_unit_id: str,
        target: WorkUnitStatus,
        actor_id: str,
        *,
        blocked_reason: str | None = None,
        output_ids: tuple[str, ...] = (),
        reason: str | None = None,
    ) -> WorkUnit:
        """Apply one governed transition, with the rules that need the graph or the log.

        - Every transition names its actor.
        - ``ready`` waits until every dependency holds an accepted output.
        - Submission (``running -> machine_qa``) names the outputs it claims,
          and only submission records outputs.
        - Whoever submitted the attempt, or executed it, cannot accept it.
        - Correction, escalation and cancellation state a reason.
        """
        if not actor_id:
            raise WorkUnitError("every work unit transition must identify its actor")
        work_unit = self.work_units[work_unit_id]
        submission = work_unit.state is WorkUnitStatus.RUNNING and target is WorkUnitStatus.MACHINE_QA
        if target is WorkUnitStatus.READY:
            waiting = self.unaccepted_dependencies(work_unit_id)
            if waiting:
                raise WorkUnitError(f"{work_unit_id} is not ready: waiting on {', '.join(waiting)}")
        if submission:
            if not output_ids:
                raise WorkUnitError("a submission must name the outputs it claims to have produced")
            if len(set(output_ids)) != len(output_ids):
                raise WorkUnitError("submitted output identifiers must be unique")
        elif output_ids:
            raise WorkUnitError("outputs are recorded only on submission")
        if target is WorkUnitStatus.ACCEPTED and actor_id in {self.work_unit_submitters.get(work_unit_id), work_unit.executor_id}:
            raise WorkUnitError("the actor who executed or submitted a work unit cannot accept it")
        if target in REASON_REQUIRED and not reason:
            raise WorkUnitError(f"moving to {target.value} requires a reason")
        updated = work_unit.advance(target, blocked_reason=blocked_reason)
        self.work_units[work_unit_id] = updated
        if submission:
            self.work_unit_submitters[work_unit_id] = actor_id
        payload: dict[str, Any] = {"from": work_unit.state.value, "to": target.value, "blockedReason": updated.blocked_reason}
        if output_ids:
            payload["outputIds"] = list(output_ids)
        if reason is not None:
            payload["reason"] = reason
        self._emit("work_unit.transitioned", work_unit_id, payload, actor_id)
        return updated

    def unaccepted_dependencies(self, work_unit_id: str) -> tuple[str, ...]:
        """Dependencies that do not yet hold an accepted output."""
        return tuple(
            dependency
            for dependency in self.work_units[work_unit_id].dependency_ids
            if self.work_units[dependency].state not in ACCEPTED_STATES
        )

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
    def from_events(cls, events: Iterable[dict[str, Any]], *, event_log: EventLog | None = None, strict: bool = True) -> "ControlPlane":
        """Rebuild derived state by reducing the append-only log.

        The replayed plane is built with no log attached, so replay never
        re-emits what it is reading. ``event_log`` is attached to the result for
        subsequent live use. ``strict`` refuses a log containing an event type
        this build does not know, rather than reducing it into a state that
        silently omits whatever those events said.
        """
        plane = cls()
        for event in events:
            try:
                plane._apply(event, strict=strict)
            except ReplayError:
                raise
            except (KeyError, ValueError) as error:
                raise ReplayError(
                    f"cannot replay {event.get('eventType')!r} for {event.get('aggregateId')!r}: {error}"
                ) from error
        plane.event_log = event_log
        return plane

    def _apply(self, event: dict[str, Any], *, strict: bool = True) -> None:
        if not owns_event(event, CONTROL_PLANE_EVENT_TYPES, strict=strict):
            self.unapplied_events.append(event)
            return
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
        elif event_type == "work_unit.created":
            self.add_work_unit(WorkUnit.from_dict(payload))
        elif event_type == "work_unit.assigned":
            self.assign_work_unit(aggregate_id, payload["executorId"], actor_id or "")
        elif event_type == "work_unit.transitioned":
            self.advance_work_unit(
                aggregate_id,
                WorkUnitStatus(payload["to"]),
                actor_id or "",
                blocked_reason=payload.get("blockedReason"),
                output_ids=tuple(payload.get("outputIds", [])),
                reason=payload.get("reason"),
            )
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

    def replay_matches(self, events: Iterable[dict[str, Any]]) -> bool:
        """Whether reducing the log reproduces this plane's derived state."""
        return self.state() == ControlPlane.from_events(events).state()

    def state(self) -> dict[str, Any]:
        """The derived state, in the portable shape, for comparison and export."""
        return {
            "obligations": {key: value.value for key, value in sorted(self.obligation_states.items())},
            "workPackages": {key: value.to_dict() for key, value in sorted(self.work_packages.items())},
            "workUnits": {key: value.to_dict() for key, value in sorted(self.work_units.items())},
            "reviews": [review.to_dict() for review in self.reviews],
            "values": {key: value.to_dict() for key, value in sorted(self.values.items())},
        }
