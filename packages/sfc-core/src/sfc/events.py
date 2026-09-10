"""Append-only domain event log for local and adapter-backed runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid


class ReplayError(ValueError):
    """Raised when an event log cannot be reduced into a valid state."""


#: Every event type this build emits, grouped by the projection that reduces it.
CONTROL_PLANE_EVENT_TYPES = frozenset({
    "obligation.discovered",
    "obligation.transitioned",
    "work_package.created",
    "work_package.transitioned",
    "review.added",
    "value.created",
    "value.transitioned",
})

EVIDENCE_ROOM_EVENT_TYPES = frozenset({
    "document.version.added",
    "evidence.added",
    "evidence.transitioned",
})

#: Recorded for the activity feed and for audit, but reduced into no state.
OBSERVATIONAL_EVENT_TYPES = frozenset({"determination.produced"})

KNOWN_EVENT_TYPES = CONTROL_PLANE_EVENT_TYPES | EVIDENCE_ROOM_EVENT_TYPES | OBSERVATIONAL_EVENT_TYPES


def owns_event(event: dict[str, Any], owned: frozenset[str], *, strict: bool = True) -> bool:
    """Whether a projection reduces this event, refusing one it cannot place.

    Replay has three cases to tell apart, and only a registry can tell them:

        owned      apply it
        foreign    another projection reduces it; record and move on
        unknown    refuse the log

    A reducer without the registry cannot distinguish the last two, so it
    ignores both and then reports a successful replay of a log whose unread
    events may well have been state-affecting. The replay is syntactically
    complete and semantically partial, which is the one failure mode a rebuilt
    projection must not have.

    So an event type this build has never heard of fails closed: the log was
    written by something that knows more than this reducer does, and the state
    rebuilt from it is not the state that was recorded. ``strict=False`` is for
    a caller that has decided to inspect a forward-version log anyway.
    """
    event_type = str(event.get("eventType", ""))
    if event_type in owned:
        return True
    if event_type in KNOWN_EVENT_TYPES:
        return False
    if strict:
        raise ReplayError(
            f"unrecognized event type {event_type!r} for {event.get('aggregateId')!r}: "
            "a log with unread events cannot be reduced into the state it recorded"
        )
    return False


@dataclass(frozen=True)
class Event:
    event_type: str
    aggregate_id: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    actor_id: str | None = None
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {"eventId": self.event_id, "eventType": self.event_type, "occurredAt": self.occurred_at, "aggregateId": self.aggregate_id, "actorId": self.actor_id, "payload": self.payload}


class EventLog:
    def __init__(self, path: str | Path = ".sfc/events.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: Event) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")

    def read(self, aggregate_id: str | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [event for event in events if aggregate_id is None or event.get("aggregateId") == aggregate_id]

