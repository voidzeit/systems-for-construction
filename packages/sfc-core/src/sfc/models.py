"""Small immutable-ish domain contracts used by all SFC adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import hashlib
import json


class Quantifier(StrEnum):
    ALL = "ALL"
    ANY = "ANY"
    NONE = "NONE"
    COUNT = "COUNT"


class DeterminationStatus(StrEnum):
    MET = "MET"
    NOT_MET = "NOT_MET"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"
    INCOMPLETE = "INCOMPLETE"
    STALE = "STALE"


#: Statuses that close a requirement. Everything else leaves it open.
CLOSING_STATUSES = frozenset({
    DeterminationStatus.MET,
    DeterminationStatus.NOT_MET,
    DeterminationStatus.NOT_APPLICABLE,
})


class DeterminationReason(StrEnum):
    """Machine-readable codes explaining why a determination reached its status."""

    EMPTY_POPULATION_UNRESOLVED = "EMPTY_POPULATION_UNRESOLVED"
    EMPTY_POPULATION_APPLICABILITY_UNEVIDENCED = "EMPTY_POPULATION_APPLICABILITY_UNEVIDENCED"
    POPULATION_BELOW_MINIMUM = "POPULATION_BELOW_MINIMUM"
    NOT_APPLICABLE_EVIDENCED = "NOT_APPLICABLE_EVIDENCED"
    MISSING_OBSERVATION = "MISSING_OBSERVATION"
    PREDICATE_NOT_EVALUABLE = "PREDICATE_NOT_EVALUABLE"
    UNRESOLVED_MEASUREMENT_UNIT = "UNRESOLVED_MEASUREMENT_UNIT"
    UNKNOWN_MEASUREMENT_UNIT = "UNKNOWN_MEASUREMENT_UNIT"
    INCOMPATIBLE_MEASUREMENT_DIMENSION = "INCOMPATIBLE_MEASUREMENT_DIMENSION"


class EmptyPopulationPolicy(StrEnum):
    """What an author declares an empty population is allowed to mean."""

    INCOMPLETE = "incomplete"
    NOT_APPLICABLE = "not_applicable"


class EvidenceSourceType(StrEnum):
    MODEL_ELEMENT = "model_element"
    PARAMETER = "parameter"
    SCHEDULE_CELL = "schedule_cell"
    PDF_PAGE = "pdf_page"
    PDF_REGION = "pdf_region"
    DRAWING_NOTE = "drawing_note"
    TABLE = "table"
    VISUAL_OBSERVATION = "visual_observation"
    EXTERNAL_DOCUMENT = "external_document"
    API_RESULT = "api_result"
    CALCULATED_FACT = "calculated_fact"
    POINT_CLOUD_SEGMENT = "point_cloud_segment"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    title: str
    statement: str
    source_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirementId": self.requirement_id,
            "title": self.title,
            "statement": self.statement,
            "sourceId": self.source_id,
        }


@dataclass(frozen=True)
class Obligation:
    obligation_id: str
    requirement: Requirement
    quantifier: Quantifier
    population: dict[str, Any]
    predicate: dict[str, Any]
    required_evidence: bool = True
    rule_set_version: str = "sfc-assurance-1"
    measurement: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Obligation":
        requirement = value.get("requirement", value)
        return cls(
            obligation_id=value.get("obligationId", value.get("requirementId", requirement.get("requirementId", ""))),
            requirement=Requirement(
                requirement_id=requirement.get("requirementId", value.get("requirementId", "")),
                title=requirement.get("title", value.get("title", "")),
                statement=requirement.get("statement", value.get("statement", "")),
                source_id=requirement.get("sourceId"),
            ),
            quantifier=Quantifier(value.get("quantifier", "ALL")),
            population=dict(value.get("population", {})),
            predicate=dict(value.get("predicate", {})),
            required_evidence=bool(value.get("requiredEvidence", True)),
            rule_set_version=value.get("ruleSetVersion", "sfc-assurance-1"),
            measurement=dict(value.get("measurement", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligationId": self.obligation_id,
            "requirement": self.requirement.to_dict(),
            "quantifier": self.quantifier.value,
            "population": self.population,
            "predicate": self.predicate,
            "requiredEvidence": self.required_evidence,
            "ruleSetVersion": self.rule_set_version,
            "measurement": self.measurement,
        }


@dataclass(frozen=True)
class Applicability:
    """Whether a requirement applies at all, and what evidences that."""

    applicable: bool | None = None
    evidence_ids: tuple[str, ...] = ()
    basis: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "Applicability":
        value = value or {}
        applicable = value.get("applicable")
        return cls(
            applicable=None if applicable is None else bool(applicable),
            evidence_ids=tuple(value.get("evidenceIds", [])),
            basis=value.get("basis"),
        )

    @property
    def proven_not_applicable(self) -> bool:
        """Non-applicability only counts when the absence itself is evidenced."""
        return self.applicable is False and bool(self.evidence_ids)

    def to_dict(self) -> dict[str, Any]:
        return {"applicable": self.applicable, "evidenceIds": list(self.evidence_ids), "basis": self.basis}


@dataclass(frozen=True)
class PopulationSpec:
    """The parsed subject-selection half of an obligation.

    ``minimum_expected`` and ``empty_population_policy`` exist so that an author
    can state how many subjects the requirement presupposes. A population that
    falls short of that never closes, because SFC cannot tell an inapplicable
    requirement apart from a model that failed to load the relevant discipline.
    """

    kind: str | None = None
    where: dict[str, Any] = field(default_factory=dict)
    minimum_expected: int = 0
    empty_population_policy: EmptyPopulationPolicy = EmptyPopulationPolicy.INCOMPLETE
    applicability: Applicability = field(default_factory=Applicability)
    assumptions: tuple[Any, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "PopulationSpec":
        value = value or {}
        return cls(
            kind=value.get("kind"),
            where=dict(value.get("where", {})),
            minimum_expected=max(0, int(value.get("minimumExpected", 0))),
            empty_population_policy=EmptyPopulationPolicy(value.get("emptyPopulationPolicy", "incomplete")),
            applicability=Applicability.from_dict(value.get("applicability")),
            assumptions=tuple(value.get("assumptions", [])),
        )


@dataclass(frozen=True)
class WorldElement:
    element_id: str
    kind: str
    properties: dict[str, Any]
    evidence_by_property: dict[str, tuple[str, ...]] = field(default_factory=dict)
    source_id: str | None = None
    geometry: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WorldElement":
        evidence = value.get("evidence", value.get("evidenceByProperty", {}))
        return cls(
            element_id=value.get("elementId", value.get("id", "")),
            kind=value.get("kind", "unknown"),
            properties=dict(value.get("properties", {})),
            evidence_by_property={key: tuple(items) for key, items in evidence.items()},
            source_id=value.get("sourceId"),
            geometry=dict(value.get("geometry", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "elementId": self.element_id,
            "kind": self.kind,
            "properties": self.properties,
            "evidence": {key: list(value) for key, value in self.evidence_by_property.items()},
            "sourceId": self.source_id,
            "geometry": self.geometry,
        }


@dataclass(frozen=True)
class ProjectWorld:
    project_id: str
    elements: tuple[WorldElement, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    frozen_at: str | None = None
    relationships: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProjectWorld":
        return cls(
            project_id=value.get("projectId", ""),
            elements=tuple(WorldElement.from_dict(item) for item in value.get("elements", [])),
            metadata=dict(value.get("metadata", {})),
            frozen_at=value.get("frozenAt"),
            relationships=tuple(value.get("relationships", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "elements": [element.to_dict() for element in self.elements],
            "metadata": self.metadata,
            "frozenAt": self.frozen_at,
            "relationships": list(self.relationships),
        }

    def snapshot_hash(self) -> str:
        return _hash(self.to_dict())


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_id: str
    source_type: EvidenceSourceType
    locator: dict[str, Any]
    observed_value: Any
    authority: float
    confidence: float
    provenance: tuple[str, ...]
    timestamp: str = field(default_factory=_utc_now)
    freshness: str | None = None
    limitations: tuple[str, ...] = ()
    admitted: bool = False
    measurement: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Evidence":
        return cls(
            evidence_id=value.get("evidenceId", ""),
            source_id=value.get("sourceId", ""),
            source_type=EvidenceSourceType(value.get("sourceType", "calculated_fact")),
            locator=dict(value.get("locator", {})),
            observed_value=value.get("observedValue"),
            authority=float(value.get("authority", 0.0)),
            confidence=float(value.get("confidence", 0.0)),
            provenance=tuple(value.get("provenance", [])),
            timestamp=value.get("timestamp", _utc_now()),
            freshness=value.get("freshness"),
            limitations=tuple(value.get("limitations", [])),
            admitted=bool(value.get("admitted", False)),
            measurement=value.get("measurement"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidenceId": self.evidence_id,
            "sourceId": self.source_id,
            "sourceType": self.source_type.value,
            "locator": self.locator,
            "observedValue": self.observed_value,
            "authority": self.authority,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "provenance": list(self.provenance),
            "timestamp": self.timestamp,
            "limitations": list(self.limitations),
            "admitted": self.admitted,
            "measurement": self.measurement,
        }


@dataclass(frozen=True)
class Counterexample:
    subject: str
    observed: Any
    expected: Any
    evidence_ids: tuple[str, ...] = ()
    reason: str | None = None
    measurement: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Counterexample":
        return cls(value.get("subject", ""), value.get("observed"), value.get("expected"), tuple(value.get("evidenceIds", [])), value.get("reason"), value.get("measurement"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "observed": self.observed,
            "expected": self.expected,
            "evidenceIds": list(self.evidence_ids),
            "reason": self.reason,
            "measurement": self.measurement,
        }


@dataclass(frozen=True)
class Determination:
    requirement_id: str
    obligation_id: str
    quantifier: Quantifier
    expected_population: int
    evaluated_population: int
    conforming: int
    coverage: float | None
    status: DeterminationStatus
    counterexamples: tuple[Counterexample, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    assumptions: tuple[Any, ...] = ()
    contradictions: tuple[str, ...] = ()
    generated_at: str = field(default_factory=_utc_now)
    rule_set_version: str = "sfc-assurance-1"
    reasons: tuple[str, ...] = ()
    applicability: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Determination":
        population = value.get("population", {})
        return cls(
            value.get("requirementId", ""),
            value.get("obligationId", ""),
            Quantifier(value.get("quantifier", "ALL")),
            int(population.get("expected", 0)),
            int(population.get("evaluated", 0)),
            int(value.get("conforming", 0)),
            None if value.get("coverage") is None else float(value["coverage"]),
            DeterminationStatus(value.get("determination", "UNKNOWN")),
            tuple(Counterexample.from_dict(item) for item in value.get("counterexamples", [])),
            tuple(value.get("evidenceIds", [])),
            tuple(value.get("unknowns", [])),
            tuple(value.get("assumptions", [])),
            tuple(value.get("contradictions", [])),
            value.get("generatedAt", _utc_now()),
            value.get("ruleSetVersion", "sfc-assurance-1"),
            tuple(value.get("reasons", [])),
            value.get("applicability"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirementId": self.requirement_id,
            "obligationId": self.obligation_id,
            "quantifier": self.quantifier.value,
            "population": {
                "expected": self.expected_population,
                "evaluated": self.evaluated_population,
            },
            "coverage": self.coverage,
            "conforming": self.conforming,
            "counterexamples": [item.to_dict() for item in self.counterexamples],
            "evidenceIds": list(self.evidence_ids),
            "unknowns": list(self.unknowns),
            "assumptions": list(self.assumptions),
            "contradictions": list(self.contradictions),
            "determination": self.status.value,
            "reasons": list(self.reasons),
            "applicability": self.applicability,
            "generatedAt": self.generated_at,
            "ruleSetVersion": self.rule_set_version,
        }


@dataclass(frozen=True)
class Run:
    run_id: str
    project_id: str
    input_hash: str
    determination: Determination
    status: str = "published"
    created_at: str = field(default_factory=_utc_now)
    evidence_ids: tuple[str, ...] = ()
    proof: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "projectId": self.project_id,
            "inputHash": self.input_hash,
            "status": self.status,
            "createdAt": self.created_at,
            "evidenceIds": list(self.evidence_ids),
            "proof": self.proof,
            "determination": self.determination.to_dict(),
        }
