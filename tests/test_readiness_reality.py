import unittest

from sfc.models import Determination, DeterminationStatus, Evidence, EvidenceSourceType, Quantifier, WorldElement
from sfc.readiness import compute_readiness
from sfc.reality import RealityObservation, compare_position


class ReadinessRealityTests(unittest.TestCase):
    def test_readiness_reports_components_and_resource_contributions(self) -> None:
        determination = Determination("REQ-1", "OBL-1", Quantifier.ALL, 2, 2, 1, 1.0, DeterminationStatus.NOT_MET, evidence_ids=("EV-1",), unknowns=())
        evidence = Evidence("EV-1", "drawing", EvidenceSourceType.PDF_REGION, {"page": 1}, "observed", .9, .9, ("sha256:abc",), freshness="current")
        report = compute_readiness((determination,), (evidence,))
        self.assertEqual(report.score, 100.0)
        self.assertEqual(report.metrics["evidenceGrounded"], 1.0)
        self.assertTrue(any(item.resource_id == "EV-1" for item in report.contributions))

    def test_reality_comparison_preserves_missing_geometry_as_unknown(self) -> None:
        expected = WorldElement("P-1", "panel", {}, geometry={"position": [0, 0, 0]})
        observed = RealityObservation("OBS-1", "scan-1", "point_cloud_segment", {"installed": True}, element_id="P-1", geometry={"position": [0.2, 0, 0]}, locator={"segment": "seg-1"}, provenance=("sha256:scan",), confidence=.96)
        comparison = compare_position(expected, observed, .1)
        self.assertEqual(comparison.status, DeterminationStatus.NOT_MET)
        self.assertEqual(comparison.deviation, .2)
        self.assertEqual(observed.to_evidence().source_type, EvidenceSourceType.POINT_CLOUD_SEGMENT)
        self.assertEqual(compare_position(WorldElement("P-2", "panel", {}), observed, .1).status, DeterminationStatus.UNKNOWN)

