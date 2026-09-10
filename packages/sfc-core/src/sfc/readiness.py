"""Transparent project readiness and resource contribution metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .models import Determination, Evidence, DeterminationStatus


@dataclass(frozen=True)
class ReadinessContribution:
    resource_id: str
    score_delta: float
    kind: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"resourceId": self.resource_id, "scoreDelta": self.score_delta, "kind": self.kind, "reason": self.reason}


@dataclass(frozen=True)
class ReadinessReport:
    score: float | None
    metrics: dict[str, float | None]
    contributions: tuple[ReadinessContribution, ...]
    basis: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "metrics": self.metrics, "contributions": [item.to_dict() for item in self.contributions], "basis": self.basis}


def compute_readiness(determinations: Iterable[Determination], evidence: Iterable[Evidence] = ()) -> ReadinessReport:
    determinations = tuple(determinations)
    evidence = tuple(evidence)
    if not determinations:
        return ReadinessReport(None, {"requirementsCovered": None, "populationEvaluated": None, "evidenceGrounded": None, "evidenceCurrent": None, "contradictionsUnresolved": None, "unknownRate": None}, (), {"requirements": 0, "evidence": len(evidence)})
    expected = sum(max(0, item.expected_population) for item in determinations)
    evaluated = sum(max(0, min(item.evaluated_population, item.expected_population)) for item in determinations)
    covered = sum(item.status not in {DeterminationStatus.UNKNOWN, DeterminationStatus.INCOMPLETE, DeterminationStatus.STALE} for item in determinations)
    grounded = sum(bool(item.evidence_ids) for item in determinations)
    evidence_with_freshness = [item for item in evidence if item.freshness is not None]
    current_values = {"current", "fresh", "valid", "up_to_date"}
    current = sum(str(item.freshness).lower() in current_values for item in evidence_with_freshness)
    contradictions = sum(len(item.contradictions) for item in determinations)
    unknowns = sum(len(item.unknowns) for item in determinations)
    metrics: dict[str, float | None] = {
        "requirementsCovered": covered / len(determinations),
        "populationEvaluated": evaluated / expected if expected else None,
        "evidenceGrounded": grounded / len(determinations),
        "evidenceCurrent": current / len(evidence_with_freshness) if evidence_with_freshness else None,
        "contradictionsUnresolved": contradictions / len(determinations),
        "unknownRate": unknowns / expected if expected else None,
    }
    weighted = (("requirementsCovered", .2), ("populationEvaluated", .2), ("evidenceGrounded", .2), ("evidenceCurrent", .15), ("contradictionsUnresolved", .15), ("unknownRate", .1))
    available = [(weight, (1 - value if name in {"contradictionsUnresolved", "unknownRate"} else value)) for name, weight in weighted if (value := metrics[name]) is not None]
    score = round(100 * sum(weight * value for weight, value in available) / sum(weight for weight, _ in available), 2) if available else None
    contributions: list[ReadinessContribution] = []
    share = 100 / len(determinations)
    for item in determinations:
        contributions.append(ReadinessContribution(item.requirement_id, round(share * float(metrics["requirementsCovered"] or 0), 3), "requirement_coverage", f"Determination status: {item.status.value}"))
        for evidence_id in item.evidence_ids:
            contributions.append(ReadinessContribution(evidence_id, round(.2 * share / max(1, len(item.evidence_ids)), 3), "evidence_grounding", "Evidence grounds a determination"))
        if item.unknowns:
            contributions.append(ReadinessContribution(item.requirement_id, round(-.1 * share, 3), "unknowns", "Requirement has unresolved unknowns"))
        if item.contradictions:
            contributions.append(ReadinessContribution(item.requirement_id, round(-.15 * share, 3), "contradictions", "Requirement has unresolved contradictions"))
    return ReadinessReport(score, metrics, tuple(contributions), {"requirements": len(determinations), "evidence": len(evidence), "expectedPopulation": expected, "evaluatedPopulation": evaluated})
