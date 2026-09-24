"""Product-facing activity and task projections over append-only events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ActionTask:
    task_id: str
    title: str
    target_id: str
    kind: str
    status: str = "open"
    source_event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"taskId": self.task_id, "title": self.title, "targetId": self.target_id, "kind": self.kind, "status": self.status, "sourceEventId": self.source_event_id}


#: Human-readable labels for the event types the control plane emits. An event
#: type with no entry keeps its own name rather than being relabelled or hidden.
EVENT_LABELS = {
    "obligation.discovered": "Obligation discovered",
    "obligation.transitioned": "Obligation advanced",
    "work_package.created": "Work package created",
    "work_package.transitioned": "Work package advanced",
    "work_unit.created": "Work unit planned",
    "work_unit.assigned": "Work unit assigned",
    "work_unit.transitioned": "Work unit advanced",
    "review.added": "Review recorded",
    "value.created": "Value recorded",
    "value.transitioned": "Value advanced",
    "evidence.added": "Evidence added",
    "evidence.transitioned": "Evidence advanced",
    "determination.produced": "Determination produced",
}


def activity_feed(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order the append-only log newest first and label each entry.

    This is a projection over the log, not a replacement for it: nothing is
    dropped, merged or rewritten, and an unrecognized event type keeps its own
    name so a new event is visible before its label exists.
    """
    projected = [
        {**event, "label": EVENT_LABELS.get(str(event.get("eventType", "")), str(event.get("eventType", "")))}
        for event in events
    ]
    # A stable sort keeps append order for events sharing a timestamp.
    return sorted(projected, key=lambda event: str(event.get("occurredAt", "")), reverse=True)


def derive_tasks(events: Iterable[dict[str, Any]]) -> list[ActionTask]:
    tasks: list[ActionTask] = []
    for event in events:
        event_type = event.get("eventType", "")
        target_id = str(event.get("aggregateId", ""))
        payload = event.get("payload", {})
        if event_type == "evidence.added" and payload.get("state") == "pending_review":
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Review pending evidence", target_id, "evidence_review", source_event_id=event.get("eventId")))
        elif event_type == "evidence.transitioned" and payload.get("to") == "pending_review":
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Review pending evidence", target_id, "evidence_review", source_event_id=event.get("eventId")))
        elif event_type == "obligation.discovered":
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Classify obligation", target_id, "obligation_classification", source_event_id=event.get("eventId")))
        elif event_type == "work_package.created":
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Advance work package", target_id, "work_package", source_event_id=event.get("eventId")))
        elif event_type == "work_unit.transitioned" and payload.get("to") == "human_review":
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Review submitted work", target_id, "work_unit_review", source_event_id=event.get("eventId")))
        elif event_type == "work_unit.transitioned" and payload.get("to") == "escalated":
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Resolve escalated work", target_id, "work_unit_escalation", source_event_id=event.get("eventId")))
        elif event_type == "determination.produced" and payload.get("status") == "NOT_MET":
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Inspect determination counterexample", target_id, "counterexample_review", source_event_id=event.get("eventId")))
        elif event_type == "determination.produced" and payload.get("status") in {"UNKNOWN", "INCOMPLETE", "STALE"}:
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Resolve incomplete requirement", target_id, "requirement_resolution", source_event_id=event.get("eventId")))
    return tasks
