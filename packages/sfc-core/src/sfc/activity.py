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


def activity_feed(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(events)


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
        elif event_type == "determination.produced" and payload.get("status") == "NOT_MET":
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Inspect determination counterexample", target_id, "counterexample_review", source_event_id=event.get("eventId")))
        elif event_type == "determination.produced" and payload.get("status") in {"UNKNOWN", "INCOMPLETE", "STALE"}:
            tasks.append(ActionTask(f"task-{event.get('eventId')}", "Resolve incomplete requirement", target_id, "requirement_resolution", source_event_id=event.get("eventId")))
    return tasks
