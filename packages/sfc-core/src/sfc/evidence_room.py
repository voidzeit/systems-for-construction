"""Versioned evidence and document-room lifecycle boundaries.

Like the control plane, this is reference semantics rather than a durable
service: state lives in memory and the event log is the only thing that
persists. Both projections are therefore reductions of the same log, and both
have to be rebuildable from it, or the log is only half an audit trail:

                            EventLog
                               |
                +--------------+--------------+
                |                             |
          ControlPlane                  EvidenceRoom
        obligations, work,          document versions,
        reviews, value              evidence state history

``from_events`` applies the same transition rules as live execution, and the
events carry enough to rebuild without guessing: a transition records the
resulting timestamp, and an admission records the authority threshold it was
held to, so a replay cannot quietly substitute a default for the policy that
was actually applied.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Iterable
import hashlib

from .authority import EvidenceAuthority
from .events import EVIDENCE_ROOM_EVENT_TYPES, Event, EventLog, ReplayError, owns_event
from .models import Evidence, _utc_now


class EvidenceState(StrEnum):
    OBSERVED = "observed"
    CANDIDATE = "candidate"
    PENDING_REVIEW = "pending_review"
    ADMITTED = "admitted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    STALE = "stale"
    CONTRADICTED = "contradicted"
    REVOKED = "revoked"
    DUPLICATE = "duplicate"


class DocumentState(StrEnum):
    OBSERVED = "observed"
    VALIDATED = "validated"
    REQUIRING_ACTION = "requiring_action"
    EXPIRED = "expired"
    REPLACED = "replaced"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class DocumentVersion:
    document_id: str
    version_id: str
    name: str
    source_id: str
    content_hash: str
    size_bytes: int
    uploaded_by: str | None = None
    state: DocumentState = DocumentState.OBSERVED
    created_at: str = field(default_factory=_utc_now)
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DocumentVersion":
        return cls(
            document_id=value["documentId"],
            version_id=value["versionId"],
            name=value.get("name", ""),
            source_id=value.get("sourceId", value["documentId"]),
            content_hash=value["contentHash"],
            size_bytes=int(value.get("sizeBytes", 0)),
            uploaded_by=value.get("uploadedBy"),
            state=DocumentState(value.get("state", DocumentState.OBSERVED.value)),
            created_at=value.get("createdAt", _utc_now()),
            metadata=value.get("metadata") or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {"documentId": self.document_id, "versionId": self.version_id, "name": self.name, "sourceId": self.source_id, "contentHash": self.content_hash, "sizeBytes": self.size_bytes, "uploadedBy": self.uploaded_by, "state": self.state.value, "createdAt": self.created_at, "metadata": self.metadata or {}}


@dataclass(frozen=True)
class EvidenceEnvelope:
    evidence: Evidence
    state: EvidenceState
    version_id: str | None = None
    supersedes_evidence_id: str | None = None
    updated_at: str = field(default_factory=_utc_now)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EvidenceEnvelope":
        return cls(
            evidence=Evidence.from_dict(value["evidence"]),
            state=EvidenceState(value["state"]),
            version_id=value.get("versionId"),
            supersedes_evidence_id=value.get("supersedesEvidenceId"),
            updated_at=value.get("updatedAt", _utc_now()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"evidence": self.evidence.to_dict(), "state": self.state.value, "versionId": self.version_id, "supersedesEvidenceId": self.supersedes_evidence_id, "updatedAt": self.updated_at}


_EVIDENCE_TRANSITIONS: dict[EvidenceState, set[EvidenceState]] = {
    EvidenceState.OBSERVED: {EvidenceState.CANDIDATE, EvidenceState.DUPLICATE},
    EvidenceState.CANDIDATE: {EvidenceState.PENDING_REVIEW, EvidenceState.REJECTED, EvidenceState.DUPLICATE},
    EvidenceState.PENDING_REVIEW: {EvidenceState.ADMITTED, EvidenceState.REJECTED, EvidenceState.CONTRADICTED},
    EvidenceState.ADMITTED: {EvidenceState.SUPERSEDED, EvidenceState.STALE, EvidenceState.CONTRADICTED, EvidenceState.REVOKED},
    EvidenceState.SUPERSEDED: set(),
    EvidenceState.REJECTED: set(),
    EvidenceState.STALE: set(),
    EvidenceState.CONTRADICTED: {EvidenceState.REVOKED, EvidenceState.SUPERSEDED},
    EvidenceState.REVOKED: set(),
    EvidenceState.DUPLICATE: set(),
}


class EvidenceRoom:
    """Reference in-memory room with append-only event history."""

    def __init__(self, event_log: EventLog | None = None) -> None:
        self.event_log = event_log
        self.versions: dict[str, list[DocumentVersion]] = {}
        self.evidence: dict[str, EvidenceEnvelope] = {}
        #: Events another projection owns, recorded rather than dropped. An
        #: event type no projection owns is refused; see ``owns_event``.
        self.unapplied_events: list[dict[str, Any]] = []

    def add_document_version(self, document_id: str, name: str, content: bytes | str, *, source_id: str | None = None, uploaded_by: str | None = None, metadata: dict[str, Any] | None = None) -> DocumentVersion:
        payload = content.encode("utf-8") if isinstance(content, str) else content
        content_hash = hashlib.sha256(payload).hexdigest()
        existing = next((item for item in self.versions.get(document_id, []) if item.content_hash == content_hash), None)
        if existing:
            return existing
        prior = self.versions.get(document_id, [])
        if prior:
            self.versions[document_id] = [replace(item, state=DocumentState.REPLACED) for item in prior]
        version = DocumentVersion(document_id, f"{document_id}:{content_hash[:12]}", name, source_id or document_id, content_hash, len(payload), uploaded_by, metadata=metadata)
        self.versions.setdefault(document_id, []).append(version)
        self._emit("document.version.added", document_id, version.to_dict(), uploaded_by)
        return version

    def add_evidence(self, evidence: Evidence, *, version_id: str | None = None, state: EvidenceState = EvidenceState.CANDIDATE) -> EvidenceEnvelope:
        if evidence.evidence_id in self.evidence:
            raise ValueError(f"evidence already exists: {evidence.evidence_id}")
        if version_id and not any(version.version_id == version_id for versions in self.versions.values() for version in versions):
            raise ValueError(f"document version not found: {version_id}")
        envelope = EvidenceEnvelope(evidence, state, version_id=version_id)
        self.evidence[evidence.evidence_id] = envelope
        self._emit("evidence.added", evidence.evidence_id, envelope.to_dict())
        return envelope

    def submit_for_review(self, evidence_id: str) -> EvidenceEnvelope:
        return self.transition(evidence_id, EvidenceState.PENDING_REVIEW)

    def admit(self, evidence_id: str, authority: EvidenceAuthority | None = None, *, actor_id: str | None = None, at: str | None = None) -> EvidenceEnvelope:
        envelope = self.evidence[evidence_id]
        if envelope.state is not EvidenceState.PENDING_REVIEW:
            raise ValueError("only pending evidence can be admitted")
        authority = authority or EvidenceAuthority()
        admitted = authority.admit(envelope.evidence)
        # The threshold is recorded because it is a policy input, not a
        # property of the evidence. Without it a replay would hold the log to
        # whatever default this build ships rather than to the rule applied.
        return self.transition(
            evidence_id,
            EvidenceState.ADMITTED,
            actor_id=actor_id,
            evidence=admitted,
            at=at,
            policy={"minimumAuthority": authority.minimum_authority},
        )

    def transition(self, evidence_id: str, target: EvidenceState, *, actor_id: str | None = None, evidence: Evidence | None = None, supersedes_evidence_id: str | None = None, at: str | None = None, policy: dict[str, Any] | None = None) -> EvidenceEnvelope:
        current = self.evidence[evidence_id]
        if target not in _EVIDENCE_TRANSITIONS[current.state]:
            raise ValueError(f"invalid evidence transition: {current.state} -> {target}")
        if target is EvidenceState.REVOKED and not supersedes_evidence_id:
            raise ValueError("revocation must identify the superseded evidence")
        updated = EvidenceEnvelope(evidence or current.evidence, target, current.version_id, supersedes_evidence_id, at or _utc_now())
        self.evidence[evidence_id] = updated
        self._emit("evidence.transitioned", evidence_id, {
            "from": current.state.value,
            "to": target.value,
            "supersedesEvidenceId": supersedes_evidence_id,
            # Recorded so replay restores the state as it stood, rather than
            # stamping it with the moment the log happened to be read.
            "updatedAt": updated.updated_at,
            **(policy or {}),
        }, actor_id)
        return updated

    def get(self, evidence_id: str) -> EvidenceEnvelope:
        return self.evidence[evidence_id]

    def all_versions(self, document_id: str | None = None) -> tuple[DocumentVersion, ...]:
        values = self.versions.values() if document_id is None else (self.versions.get(document_id, []),)
        return tuple(item for versions in values for item in versions)

    def to_dict(self) -> dict[str, Any]:
        return {"documents": [item.to_dict() for item in self.all_versions()], "evidence": [item.to_dict() for item in self.evidence.values()]}

    def state(self) -> dict[str, Any]:
        """The derived state, ordered, for comparison and export."""
        return {
            "documents": [
                item.to_dict()
                for item in sorted(self.all_versions(), key=lambda item: (item.document_id, item.version_id))
            ],
            "evidence": [self.evidence[key].to_dict() for key in sorted(self.evidence)],
        }

    @classmethod
    def from_events(cls, events: Iterable[dict[str, Any]], *, event_log: EventLog | None = None, strict: bool = True, authority: EvidenceAuthority | None = None) -> "EvidenceRoom":
        """Rebuild the room by reducing the append-only log.

        Built with no log attached, so replay never re-emits what it reads.
        ``authority`` is the fallback for a log written before admissions
        recorded the threshold they were held to.
        """
        room = cls()
        for event in events:
            try:
                room._apply(event, strict=strict, authority=authority)
            except ReplayError:
                raise
            except (KeyError, ValueError) as error:
                raise ReplayError(
                    f"cannot replay {event.get('eventType')!r} for {event.get('aggregateId')!r}: {error}"
                ) from error
        room.event_log = event_log
        return room

    def replay_matches(self, events: Iterable[dict[str, Any]]) -> bool:
        """Whether reducing the log reproduces this derived state."""
        return self.state() == EvidenceRoom.from_events(events).state()

    def _apply(self, event: dict[str, Any], *, strict: bool = True, authority: EvidenceAuthority | None = None) -> None:
        if not owns_event(event, EVIDENCE_ROOM_EVENT_TYPES, strict=strict):
            self.unapplied_events.append(event)
            return
        event_type = str(event.get("eventType", ""))
        aggregate_id = str(event.get("aggregateId", ""))
        payload = event.get("payload", {}) or {}
        actor_id = event.get("actorId")
        if event_type == "document.version.added":
            self._restore_version(DocumentVersion.from_dict(payload))
        elif event_type == "evidence.added":
            self._restore_evidence(EvidenceEnvelope.from_dict(payload))
        elif event_type == "evidence.transitioned":
            target = EvidenceState(payload["to"])
            at = payload.get("updatedAt")
            if target is EvidenceState.ADMITTED:
                # Replay re-applies the admission rules rather than trusting
                # the log, so a recorded but inadmissible admission fails.
                threshold = payload.get("minimumAuthority")
                self.admit(
                    aggregate_id,
                    EvidenceAuthority(float(threshold)) if threshold is not None else authority,
                    actor_id=actor_id,
                    at=at,
                )
            else:
                self.transition(
                    aggregate_id,
                    target,
                    actor_id=actor_id,
                    supersedes_evidence_id=payload.get("supersedesEvidenceId"),
                    at=at,
                )

    def _restore_version(self, version: DocumentVersion) -> None:
        prior = self.versions.get(version.document_id, [])
        if any(item.version_id == version.version_id for item in prior):
            raise ValueError(f"document version already exists: {version.version_id}")
        if prior:
            self.versions[version.document_id] = [replace(item, state=DocumentState.REPLACED) for item in prior]
        self.versions.setdefault(version.document_id, []).append(version)

    def _restore_evidence(self, envelope: EvidenceEnvelope) -> None:
        evidence_id = envelope.evidence.evidence_id
        if evidence_id in self.evidence:
            raise ValueError(f"evidence already exists: {evidence_id}")
        if envelope.version_id and not any(
            version.version_id == envelope.version_id
            for versions in self.versions.values()
            for version in versions
        ):
            raise ValueError(f"document version not found: {envelope.version_id}")
        self.evidence[evidence_id] = envelope

    def _emit(self, event_type: str, aggregate_id: str, payload: dict[str, Any], actor_id: str | None = None) -> None:
        if self.event_log:
            self.event_log.append(Event(event_type, aggregate_id, payload, actor_id=actor_id))
