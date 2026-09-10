import unittest

from sfc.assurance import AssuranceError, evaluate_obligation, validate_determination
from sfc.models import (
    Determination,
    DeterminationReason,
    DeterminationStatus,
    Obligation,
    ProjectWorld,
    Quantifier,
    Requirement,
    WorldElement,
)


def _obligation(population: dict) -> Obligation:
    return Obligation(
        obligation_id="OBL-1",
        requirement=Requirement("REQ-1", "Clearance", "Every board must maintain clearance"),
        quantifier=Quantifier.ALL,
        population=population,
        predicate={"property": "clearance", "operator": ">=", "value": 36},
    )


class EmptyPopulationTests(unittest.TestCase):
    def test_empty_world_does_not_close(self) -> None:
        determination = evaluate_obligation(_obligation({"kind": "board"}), ProjectWorld("p", ()))
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertIn(DeterminationReason.EMPTY_POPULATION_UNRESOLVED.value, determination.reasons)

    def test_missing_kind_does_not_close(self) -> None:
        world = ProjectWorld("p", (WorldElement("W-1", "wall", {"clearance": 99}),))
        determination = evaluate_obligation(_obligation({"kind": "board"}), world)
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertEqual(determination.conforming, 0)

    def test_coverage_is_absent_not_one(self) -> None:
        determination = evaluate_obligation(_obligation({"kind": "board"}), ProjectWorld("p", ()))
        self.assertIsNone(determination.coverage)
        self.assertIsNone(determination.to_dict()["coverage"])

    def test_policy_alone_cannot_close(self) -> None:
        population = {"kind": "board", "emptyPopulationPolicy": "not_applicable"}
        determination = evaluate_obligation(_obligation(population), ProjectWorld("p", ()))
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertIn(DeterminationReason.EMPTY_POPULATION_APPLICABILITY_UNEVIDENCED.value, determination.reasons)

    def test_unevidenced_applicability_claim_cannot_close(self) -> None:
        population = {"kind": "board", "applicability": {"applicable": False, "basis": "asserted only"}}
        determination = evaluate_obligation(_obligation(population), ProjectWorld("p", ()))
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)

    def test_evidenced_non_applicability_closes_as_not_applicable(self) -> None:
        population = {
            "kind": "board",
            "applicability": {"applicable": False, "evidenceIds": ["E-SCOPE-1"], "basis": "project has no electrical scope"},
        }
        determination = evaluate_obligation(_obligation(population), ProjectWorld("p", ()))
        self.assertEqual(determination.status, DeterminationStatus.NOT_APPLICABLE)
        self.assertEqual(determination.evidence_ids, ("E-SCOPE-1",))
        self.assertEqual(determination.applicability["basis"], "project has no electrical scope")
        validate_determination(determination)

    def test_population_below_minimum_does_not_close(self) -> None:
        world = ProjectWorld("p", (WorldElement("B-1", "board", {"clearance": 40}),))
        determination = evaluate_obligation(_obligation({"kind": "board", "minimumExpected": 3}), world)
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertEqual(determination.conforming, 1)
        self.assertIn(DeterminationReason.POPULATION_BELOW_MINIMUM.value, determination.reasons)

    def test_population_below_minimum_still_reports_failure(self) -> None:
        world = ProjectWorld("p", (WorldElement("B-1", "board", {"clearance": 10}),))
        determination = evaluate_obligation(_obligation({"kind": "board", "minimumExpected": 3}), world)
        self.assertEqual(determination.status, DeterminationStatus.NOT_MET)
        self.assertEqual(len(determination.counterexamples), 1)


class DeterminationInvariantTests(unittest.TestCase):
    def _determination(self, **overrides) -> Determination:
        base = dict(
            requirement_id="REQ-1",
            obligation_id="OBL-1",
            quantifier=Quantifier.ALL,
            expected_population=0,
            evaluated_population=0,
            conforming=0,
            coverage=None,
            status=DeterminationStatus.MET,
        )
        base.update(overrides)
        return Determination(**base)

    def test_met_on_empty_population_is_rejected(self) -> None:
        with self.assertRaises(AssuranceError):
            validate_determination(self._determination())

    def test_not_applicable_without_evidence_is_rejected(self) -> None:
        with self.assertRaises(AssuranceError):
            validate_determination(self._determination(status=DeterminationStatus.NOT_APPLICABLE))

    def test_not_applicable_with_population_is_rejected(self) -> None:
        with self.assertRaises(AssuranceError):
            validate_determination(self._determination(
                status=DeterminationStatus.NOT_APPLICABLE,
                expected_population=2,
                evaluated_population=2,
                coverage=1.0,
                evidence_ids=("E-1",),
            ))

    def test_absent_coverage_requires_absent_population(self) -> None:
        with self.assertRaises(AssuranceError):
            validate_determination(self._determination(
                status=DeterminationStatus.INCOMPLETE,
                expected_population=2,
                evaluated_population=0,
                coverage=None,
            ))


if __name__ == "__main__":
    unittest.main()
