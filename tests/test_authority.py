import unittest

from sfc.authority import EvidenceAdmissionError, EvidenceAuthority
from sfc.models import Evidence, EvidenceSourceType


def evidence(**overrides):
    values = {
        "evidence_id": "E-1",
        "source_id": "model-1",
        "source_type": EvidenceSourceType.MODEL_ELEMENT,
        "locator": {"elementId": "LP-1"},
        "observed_value": 36,
        "authority": 0.9,
        "confidence": 0.99,
        "provenance": ("connector:synthetic", "snapshot:abc"),
    }
    values.update(overrides)
    return Evidence(**values)


class AuthorityTests(unittest.TestCase):
    def test_admission_is_explicit(self) -> None:
        candidate = evidence()
        admitted = EvidenceAuthority().admit(candidate)
        self.assertFalse(candidate.admitted)
        self.assertTrue(admitted.admitted)

    def test_low_authority_and_missing_provenance_are_rejected(self) -> None:
        with self.assertRaises(EvidenceAdmissionError):
            EvidenceAuthority().admit(evidence(authority=0.5))
        with self.assertRaises(EvidenceAdmissionError):
            EvidenceAuthority().admit(evidence(provenance=()))

