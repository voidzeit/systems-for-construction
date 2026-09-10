"""Structured proof objects derived from determinations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Determination


@dataclass(frozen=True)
class Proof:
    requirement_id: str
    population: dict[str, int]
    coverage: float | None
    claims: tuple[dict[str, Any], ...]
    evidence: tuple[str, ...]
    witnesses: tuple[str, ...]
    counterexamples: tuple[dict[str, Any], ...]
    contradictions: tuple[str, ...]
    unknowns: tuple[dict[str, Any], ...]
    assumptions: tuple[str, ...]
    result: str
    inspected_evidence: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    @classmethod
    def from_determination(cls, determination: Determination) -> "Proof":
        claims = ({
            "statement": f"{determination.conforming} of {determination.expected_population} subjects satisfy the obligation",
            "quantifier": determination.quantifier.value,
        },)
        return cls(
            requirement_id=determination.requirement_id,
            population={"expected": determination.expected_population, "evaluated": determination.evaluated_population},
            coverage=determination.coverage,
            claims=claims,
            evidence=determination.evidence_ids,
            witnesses=determination.witnesses,
            counterexamples=tuple(item.to_dict() for item in determination.counterexamples),
            contradictions=determination.contradictions,
            unknowns=tuple(item.to_dict() for item in determination.unknowns),
            inspected_evidence=determination.inspected_evidence_ids,
            assumptions=determination.assumptions,
            result=determination.status.value,
            reasons=determination.reasons,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirementId": self.requirement_id,
            "population": self.population,
            "coverage": self.coverage,
            "claims": list(self.claims),
            "evidence": list(self.evidence),
            "inspectedEvidence": list(self.inspected_evidence),
            "witnesses": list(self.witnesses),
            "counterexamples": list(self.counterexamples),
            "contradictions": list(self.contradictions),
            "unknowns": list(self.unknowns),
            "assumptions": list(self.assumptions),
            "result": self.result,
            "reasons": list(self.reasons),
        }

