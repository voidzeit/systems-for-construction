"""Append-only domain event log for local and adapter-backed runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid


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

