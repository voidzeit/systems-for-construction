import unittest
from pathlib import Path

from sfc.assurance import evaluate_obligation
from sfc.governance import Review, ReviewDecision, ValueRecord, current_review
from sfc.io import load_obligation, load_world
from sfc.lifecycle import ValueStatus
from sfc.proofs import Proof


ROOT = Path(__file__).parents[1]


class ProofAndGovernanceTests(unittest.TestCase):
    def test_proof_preserves_population_and_counterexample(self) -> None:
        determination = evaluate_obligation(
            load_obligation(ROOT / "examples/electrical-panel-clearance/requirement.json"),
            load_world(ROOT / "examples/electrical-panel-clearance/project-world.json"),
        )
        proof = Proof.from_determination(determination)
        self.assertEqual(proof.population, {"expected": 18, "evaluated": 18})
        self.assertEqual(proof.counterexamples[0]["subject"], "LP-18")

    def test_review_revocation_is_append_only(self) -> None:
        accepted = Review("rev-1", "determination-1", ReviewDecision.ACCEPTED, "reviewer")
        revoked = Review("rev-2", "determination-1", ReviewDecision.REVOKED, "reviewer", supersedes_review_id="rev-1")
        self.assertIsNone(current_review([accepted, revoked], "determination-1"))

    def test_value_requires_evidence_before_earned(self) -> None:
        value = ValueRecord("value-1", "wp-1")
        value = value.advance(ValueStatus.BUDGETED)
        value = value.advance(ValueStatus.COMMITTED)
        with self.assertRaises(ValueError):
            value.advance(ValueStatus.PLANNED).advance(ValueStatus.EARNED)
        value = value.advance(ValueStatus.PLANNED).advance(ValueStatus.EARNED, evidence_ids=("e-1",))
        self.assertEqual(value.status, ValueStatus.EARNED)

