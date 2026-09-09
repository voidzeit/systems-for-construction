"""Admission boundary between candidate and official evidence."""

from dataclasses import replace

from .models import Evidence


class EvidenceAdmissionError(ValueError):
    """Raised when evidence cannot become authoritative."""


class EvidenceAuthority:
    """Apply deterministic admission rules to candidate evidence.

    Authority is a source property, not a model confidence score. The
    default threshold keeps self-reported agent observations below admitted
    evidence unless an explicit policy lowers the threshold.
    """

    def __init__(self, minimum_authority: float = 0.6) -> None:
        if not 0 <= minimum_authority <= 1:
            raise ValueError("minimum_authority must be between 0 and 1")
        self.minimum_authority = minimum_authority

    def admit(self, evidence: Evidence) -> Evidence:
        if not evidence.evidence_id or not evidence.source_id:
            raise EvidenceAdmissionError("evidenceId and sourceId are required")
        if not evidence.provenance:
            raise EvidenceAdmissionError("evidence must include provenance")
        if evidence.authority < self.minimum_authority:
            raise EvidenceAdmissionError(
                f"evidence authority {evidence.authority:.2f} is below "
                f"minimum {self.minimum_authority:.2f}"
            )
        if not 0 <= evidence.confidence <= 1:
            raise EvidenceAdmissionError("confidence must be between 0 and 1")
        return replace(evidence, admitted=True)

