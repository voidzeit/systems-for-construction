"""Evidence that grounds a conclusion is not the same as evidence looked at.

A determination that cites evidence for a subject it never decided asserts a
relationship that does not exist. These cases keep the two lists apart.
"""

from __future__ import annotations

import unittest

from sfc.assurance import evaluate_obligation
from sfc.models import (
    Determination,
    DeterminationReason,
    DeterminationStatus,
    Obligation,
    ProjectWorld,
    Quantifier,
    Requirement,
    Unresolved,
    WorldElement,
)
from sfc.proofs import Proof

OBLIGATION = Obligation(
    obligation_id="OBL-1",
    requirement=Requirement("REQ-1", "Clearance", "Every board must maintain clearance"),
    quantifier=Quantifier.ALL,
    population={"kind": "board"},
    predicate={"property": "working_clearance", "operator": ">=", "value": 36, "unit": "in"},
)

MIXED = ProjectWorld("p", (
    WorldElement("B-1", "board", {"working_clearance": {"value": 1.0668, "unit": "m"}}, {"working_clearance": ("E-1",)}),
    WorldElement("B-2", "board", {"working_clearance": {"value": 0.5, "unit": "m"}}, {"working_clearance": ("E-2",)}),
    WorldElement("B-3", "board", {"working_clearance": 29.4}, {"working_clearance": ("E-3",)}),
    WorldElement("B-4", "board", {"working_clearance": {"value": 5, "unit": "kg"}}, {"working_clearance": ("E-4",)}),
    WorldElement("B-5", "board", {}, {"working_clearance": ("E-5",)}),
))


class EvidenceSeparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.determination = evaluate_obligation(OBLIGATION, MIXED)

    def test_only_evaluated_subjects_contribute_supporting_evidence(self) -> None:
        self.assertEqual(self.determination.evidence_ids, ("E-1", "E-2"))

    def test_inspected_evidence_is_recorded_separately(self) -> None:
        self.assertEqual(self.determination.inspected_evidence_ids, ("E-3", "E-4", "E-5"))

    def test_the_two_lists_do_not_overlap(self) -> None:
        self.assertEqual(
            set(self.determination.evidence_ids) & set(self.determination.inspected_evidence_ids),
            set(),
        )

    def test_a_counterexample_still_cites_its_own_evidence(self) -> None:
        self.assertEqual(self.determination.counterexamples[0].subject, "B-2")
        self.assertEqual(self.determination.counterexamples[0].evidence_ids, ("E-2",))

    def test_each_unresolved_subject_carries_a_machine_readable_reason(self) -> None:
        by_subject = {item.subject: item for item in self.determination.unknowns}
        self.assertEqual(by_subject["B-3"].reason, DeterminationReason.UNRESOLVED_MEASUREMENT_UNIT.value)
        self.assertEqual(by_subject["B-4"].reason, DeterminationReason.INCOMPATIBLE_MEASUREMENT_DIMENSION.value)
        self.assertEqual(by_subject["B-5"].reason, DeterminationReason.MISSING_OBSERVATION.value)

    def test_each_unresolved_subject_carries_the_evidence_it_was_examined_with(self) -> None:
        by_subject = {item.subject: item for item in self.determination.unknowns}
        self.assertEqual(by_subject["B-3"].evidence_ids, ("E-3",))
        self.assertEqual(by_subject["B-5"].evidence_ids, ("E-5",))

    def test_the_detail_explains_the_failure_in_words(self) -> None:
        by_subject = {item.subject: item for item in self.determination.unknowns}
        self.assertIn("declares no unit", by_subject["B-3"].detail)
        self.assertIn("mass", by_subject["B-4"].detail)

    def test_coverage_counts_only_decided_subjects(self) -> None:
        self.assertEqual(self.determination.expected_population, 5)
        self.assertEqual(self.determination.evaluated_population, 2)
        self.assertEqual(self.determination.coverage, 0.4)

    def test_one_counterexample_closes_an_ALL_claim_despite_unknowns(self) -> None:
        # A proven violation disproves the universal claim on its own, so the
        # unresolved subjects cannot change the status - but coverage still
        # reports that most of the population was never decided.
        self.assertEqual(self.determination.status, DeterminationStatus.NOT_MET)
        self.assertLess(self.determination.coverage, 1.0)
        self.assertTrue(self.determination.unknowns)

    def test_unknowns_without_a_counterexample_leave_the_claim_open(self) -> None:
        world = ProjectWorld("p", (
            WorldElement("B-1", "board", {"working_clearance": {"value": 1.0668, "unit": "m"}}, {"working_clearance": ("E-1",)}),
            WorldElement("B-3", "board", {"working_clearance": 29.4}, {"working_clearance": ("E-3",)}),
        ))
        determination = evaluate_obligation(OBLIGATION, world)
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertEqual(determination.evidence_ids, ("E-1",))
        self.assertEqual(determination.inspected_evidence_ids, ("E-3",))

    def test_the_proof_reports_both_lists(self) -> None:
        proof = Proof.from_determination(self.determination).to_dict()
        self.assertEqual(proof["evidence"], ["E-1", "E-2"])
        self.assertEqual(proof["inspectedEvidence"], ["E-3", "E-4", "E-5"])
        self.assertEqual({item["subject"] for item in proof["unknowns"]}, {"B-3", "B-4", "B-5"})


class UnresolvedContractTests(unittest.TestCase):
    def test_it_round_trips(self) -> None:
        record = Unresolved("B-1", "MISSING_OBSERVATION", ("E-1",), "no value")
        self.assertEqual(Unresolved.from_dict(record.to_dict()), record)

    def test_a_legacy_string_unknown_still_loads(self) -> None:
        self.assertEqual(
            Unresolved.from_dict("B-1: cannot compare"),
            Unresolved("B-1", "UNSPECIFIED", (), "cannot compare"),
        )
        self.assertEqual(Unresolved.from_dict("B-1"), Unresolved("B-1", "UNSPECIFIED", (), None))

    def test_a_determination_with_legacy_unknowns_still_loads(self) -> None:
        document = self.determination_document()
        document["unknowns"] = ["B-3: no unit"]
        loaded = Determination.from_dict(document)
        self.assertEqual(loaded.unknowns[0].subject, "B-3")
        self.assertEqual(loaded.unknowns[0].reason, "UNSPECIFIED")

    def test_a_determination_round_trips_structured_unknowns(self) -> None:
        determination = evaluate_obligation(OBLIGATION, MIXED)
        self.assertEqual(Determination.from_dict(determination.to_dict()).to_dict(), determination.to_dict())

    def determination_document(self) -> dict:
        return evaluate_obligation(OBLIGATION, MIXED).to_dict()


if __name__ == "__main__":
    unittest.main()
