"""Versioned evidence and document-room lifecycle boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any
import hashlib

from .authority import EvidenceAuthority
from .events import Event, EventLog
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

    def to_dict(self) -> dict[str, Any]:
        return {"documentId": self.document_id, "versionId": self.version_id, "name": self.name, "sourceId": self.source_id, "contentHash": self.content_hash, "sizeBytes": self.size_bytes, "uploadedBy": self.uploaded_by, "state": self.state.value, "createdAt": self.created_at, "metadata": self.metadata or {}}


@dataclass(frozen=True)
class EvidenceEnvelope:
    evidence: Evidence
    state: EvidenceState
    version_id: str | None = None
    supersedes_evidence_id: str | None = None
    updated_at: str = field(default_factory=_utc_now)

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

    def admit(self, evidence_id: str, authority: EvidenceAuthority | None = None, *, actor_id: str | None = None) -> EvidenceEnvelope:
        envelope = self.evidence[evidence_id]
        if envelope.state is not EvidenceState.PENDING_REVIEW:
            raise ValueError("only pending evidence can be admitted")
        admitted = (authority or EvidenceAuthority()).admit(envelope.evidence)
        return self.transition(evidence_id, EvidenceState.ADMITTED, actor_id=actor_id, evidence=admitted)

    def transition(self, evidence_id: str, target: EvidenceState, *, actor_id: str | None = None, evidence: Evidence | None = None, supersedes_evidence_id: str | None = None) -> EvidenceEnvelope:
        current = self.evidence[evidence_id]
        if target not in _EVIDENCE_TRANSITIONS[current.state]:
            raise ValueError(f"invalid evidence transition: {current.state} -> {target}")
        if target is EvidenceState.REVOKED and not supersedes_evidence_id:
            raise ValueError("revocation must identify the superseded evidence")
        updated = EvidenceEnvelope(evidence or current.evidence, target, current.version_id, supersedes_evidence_id, _utc_now())
        self.evidence[evidence_id] = updated
        self._emit("evidence.transitioned", evidence_id, {"from": current.state.value, "to": target.value, "supersedesEvidenceId": supersedes_evidence_id}, actor_id)
        return updated

    def get(self, evidence_id: str) -> EvidenceEnvelope:
        return self.evidence[evidence_id]

    def all_versions(self, document_id: str | None = None) -> tuple[DocumentVersion, ...]:
        values = self.versions.values() if document_id is None else (self.versions.get(document_id, []),)
        return tuple(item for versions in values for item in versions)

    def to_dict(self) -> dict[str, Any]:
        return {"documents": [item.to_dict() for item in self.all_versions()], "evidence": [item.to_dict() for item in self.evidence.values()]}

    def _emit(self, event_type: str, aggregate_id: str, payload: dict[str, Any], actor_id: str | None = None) -> None:
        if self.event_log:
            self.event_log.append(Event(event_type, aggregate_id, payload, actor_id=actor_id))
