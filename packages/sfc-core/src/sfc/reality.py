"""Reality-capture observations and conservative BIM-vs-reality comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from .models import DeterminationStatus, Evidence, EvidenceSourceType, WorldElement, _utc_now


@dataclass(frozen=True)
class RealityObservation:
    observation_id: str
    source_id: str
    observation_type: str
    value: Any
    element_id: str | None = None
    geometry: dict[str, Any] | None = None
    locator: dict[str, Any] | None = None
    provenance: tuple[str, ...] = ()
    authority: float = 0.7
    confidence: float = 0.0
    observed_at: str = field(default_factory=_utc_now)

    def to_evidence(self) -> Evidence:
        if not self.provenance:
            raise ValueError("reality observation requires provenance")
        return Evidence(self.observation_id, self.source_id, EvidenceSourceType.POINT_CLOUD_SEGMENT, self.locator or {"elementId": self.element_id}, self.value, self.authority, self.confidence, self.provenance, timestamp=self.observed_at)

    def to_dict(self) -> dict[str, Any]:
        return {"observationId": self.observation_id, "sourceId": self.source_id, "observationType": self.observation_type, "value": self.value, "elementId": self.element_id, "geometry": self.geometry or {}, "locator": self.locator or {}, "provenance": list(self.provenance), "authority": self.authority, "confidence": self.confidence, "observedAt": self.observed_at}


@dataclass(frozen=True)
class RealityComparison:
    element_id: str
    observation_id: str
    status: DeterminationStatus
    deviation: float | None
    allowed_deviation: float
    evidence_ids: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"elementId": self.element_id, "observationId": self.observation_id, "status": self.status.value, "deviation": self.deviation, "allowedDeviation": self.allowed_deviation, "evidenceIds": list(self.evidence_ids), "reason": self.reason}


def compare_position(expected: WorldElement, observed: RealityObservation, allowed_deviation: float) -> RealityComparison:
    expected_position = _position(expected.geometry)
    observed_position = _position(observed.geometry or {})
    evidence_ids = (observed.observation_id,)
    if expected_position is None or observed_position is None:
        return RealityComparison(expected.element_id, observed.observation_id, DeterminationStatus.UNKNOWN, None, allowed_deviation, evidence_ids, "expected or observed position is missing")
    deviation = math.dist(expected_position, observed_position)
    status = DeterminationStatus.MET if deviation <= allowed_deviation else DeterminationStatus.NOT_MET
    return RealityComparison(expected.element_id, observed.observation_id, status, round(deviation, 6), allowed_deviation, evidence_ids, "position is within tolerance" if status is DeterminationStatus.MET else "position exceeds tolerance")


def _position(geometry: dict[str, Any]) -> tuple[float, float, float] | None:
    value = geometry.get("position", geometry.get("location"))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return tuple(float(item) for item in value[:3])
    if all(key in geometry for key in ("x", "y", "z")):
        return float(geometry["x"]), float(geometry["y"]), float(geometry["z"])
    return None
