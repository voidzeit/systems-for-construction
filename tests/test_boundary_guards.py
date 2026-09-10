"""The guards on every way into the semantic core.

Each case here is a document or an argument that a producer can construct and
that must be refused. They are grouped by the boundary that refuses them, so a
reader can see what each boundary is responsible for:

    validate_determination   an in-memory determination, before publication
    EvidenceAuthority        candidate evidence, before it becomes official
    sfc.conformance          a document from any producer, in any language
"""

from __future__ import annotations

import unittest

from sfc.assurance import AssuranceError, validate_determination
from sfc.authority import EvidenceAdmissionError, EvidenceAuthority
from sfc.conformance import determination_violations, proof_violations, run_violations
from sfc.models import (
    Counterexample,
    Determination,
    DeterminationStatus,
    Evidence,
    EvidenceSourceType,
    Quantifier,
    Unresolved,
)


def _determination(**overrides) -> Determination:
    base = dict(
        requirement_id="REQ-1",
        obligation_id="OBL-1",
        quantifier=Quantifier.ALL,
        expected_population=2,
        evaluated_population=2,
        conforming=2,
        coverage=1.0,
        status=DeterminationStatus.MET,
        witnesses=("B-1", "B-2"),
    )
    base.update(overrides)
    return Determination(**base)


def _evidence(**overrides) -> Evidence:
    base = dict(
        evidence_id="E-1",
        source_id="ifc:model-1",
        source_type=EvidenceSourceType.MODEL_ELEMENT,
        locator={"elementId": "B-1"},
        observed_value={"value": 1.0, "unit": "m"},
        authority=0.9,
        confidence=1.0,
        provenance=("project-world",),
    )
    base.update(overrides)
    return Evidence(**base)


def _violations(document: dict) -> str:
    return "\n".join(determination_violations(document))


class CountShapeTests(unittest.TestCase):
    """Counts that cannot describe any population at all."""

    def test_a_negative_count_is_refused(self) -> None:
        for field in ("expected_population", "evaluated_population"):
            with self.subTest(field=field):
                with self.assertRaises(AssuranceError) as raised:
                    validate_determination(_determination(**{field: -1}))
                self.assertIn("negative", str(raised.exception))

    def test_evaluating_more_subjects_than_exist_is_refused(self) -> None:
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(_determination(expected_population=1, evaluated_population=2, coverage=1.0))
        self.assertIn("cannot exceed expected", str(raised.exception))

    def test_more_conforming_subjects_than_evaluated_is_refused(self) -> None:
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(_determination(evaluated_population=1, conforming=2, coverage=0.5))
        self.assertIn("cannot exceed evaluated", str(raised.exception))

    def test_coverage_outside_zero_to_one_is_refused(self) -> None:
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(_determination(coverage=1.5))
        self.assertIn("between 0 and 1", str(raised.exception))

    def test_a_counterexample_bars_a_universal_met(self) -> None:
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(_determination(
                conforming=1,
                witnesses=("B-1",),
                counterexamples=(Counterexample("B-2", 1, ">= 2"),),
            ))
        self.assertIn("cannot contain a counterexample", str(raised.exception))

    def test_an_undecided_subject_bars_a_universal_met(self) -> None:
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(_determination(
                quantifier=Quantifier.COUNT,
                conforming=1,
                witnesses=("B-1",),
                unknowns=(Unresolved("B-2", "MISSING_OBSERVATION"),),
            ))
        self.assertIn("undecided", str(raised.exception))

    def test_not_applicable_cannot_carry_unresolved_subjects(self) -> None:
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(_determination(
                status=DeterminationStatus.NOT_APPLICABLE,
                expected_population=0,
                evaluated_population=0,
                conforming=0,
                coverage=None,
                witnesses=(),
                evidence_ids=("E-SCOPE",),
                unknowns=(Unresolved("B-1", "MISSING_OBSERVATION"),),
            ))
        self.assertIn("NOT_APPLICABLE cannot contain", str(raised.exception))


class AdmissionBoundaryTests(unittest.TestCase):
    """Authority is a property of the source, checked before evidence counts."""

    def test_a_threshold_outside_zero_to_one_is_refused(self) -> None:
        for threshold in (-0.1, 1.5):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    EvidenceAuthority(minimum_authority=threshold)

    def test_evidence_without_an_identity_or_a_source_is_not_admitted(self) -> None:
        for field in ("evidence_id", "source_id"):
            with self.subTest(field=field):
                with self.assertRaises(EvidenceAdmissionError) as raised:
                    EvidenceAuthority().admit(_evidence(**{field: ""}))
                self.assertIn("required", str(raised.exception))

    def test_evidence_without_provenance_is_not_admitted(self) -> None:
        with self.assertRaises(EvidenceAdmissionError) as raised:
            EvidenceAuthority().admit(_evidence(provenance=()))
        self.assertIn("provenance", str(raised.exception))

    def test_evidence_below_the_threshold_is_not_admitted(self) -> None:
        with self.assertRaises(EvidenceAdmissionError) as raised:
            EvidenceAuthority().admit(_evidence(authority=0.2))
        self.assertIn("below", str(raised.exception))

    def test_a_confidence_outside_zero_to_one_is_not_admitted(self) -> None:
        with self.assertRaises(EvidenceAdmissionError) as raised:
            EvidenceAuthority().admit(_evidence(confidence=1.4))
        self.assertIn("confidence", str(raised.exception))

    def test_admission_marks_the_evidence_and_changes_nothing_else(self) -> None:
        candidate = _evidence()
        admitted = EvidenceAuthority().admit(candidate)
        self.assertTrue(admitted.admitted)
        self.assertFalse(candidate.admitted)
        self.assertEqual(admitted.to_dict() | {"admitted": False}, candidate.to_dict())


class DocumentGuardTests(unittest.TestCase):
    """The same rules, reached through a document instead of an object."""

    def test_a_population_without_integer_counts_is_refused(self) -> None:
        self.assertIn("integer expected and evaluated", _violations(
            {"population": {"expected": "two", "evaluated": 2}, "coverage": 1.0}))

    def test_counts_that_contradict_each_other_are_reported(self) -> None:
        report = _violations({
            "quantifier": "ALL", "determination": "MET", "coverage": 1.0,
            "population": {"expected": 1, "evaluated": 2}, "conforming": 3,
        })
        self.assertIn("evaluated 2 exceeds expected 1", report)
        self.assertIn("conforming 3 exceeds evaluated 2", report)

    def test_absent_coverage_over_a_real_population_is_refused(self) -> None:
        self.assertIn("coverage is absent over a population of 2", _violations(
            {"population": {"expected": 2, "evaluated": 2}, "coverage": None}))

    def test_coverage_outside_zero_to_one_is_refused(self) -> None:
        self.assertIn("outside [0, 1]", _violations(
            {"population": {"expected": 2, "evaluated": 2}, "coverage": 1.4}))

    def test_a_repeated_evidence_identifier_is_refused(self) -> None:
        self.assertIn("evidenceIds repeats", _violations({
            "quantifier": "ALL", "determination": "MET", "coverage": 1.0,
            "population": {"expected": 2, "evaluated": 2}, "conforming": 2,
            "witnesses": ["B-1", "B-2"], "evidenceIds": ["E-1", "E-1"],
        }))

    def test_an_existential_violation_before_full_evaluation_is_refused(self) -> None:
        self.assertIn("ANY/NOT_MET before the whole population", _violations({
            "quantifier": "ANY", "determination": "NOT_MET", "coverage": 0.5,
            "population": {"expected": 2, "evaluated": 1}, "conforming": 0,
            "unknowns": [{"subject": "B-2", "reason": "MISSING_OBSERVATION"}],
        }))

    def test_a_prohibition_cannot_be_met_while_naming_a_witness(self) -> None:
        self.assertIn("NONE/MET names subject(s)", _violations({
            "quantifier": "NONE", "determination": "MET", "coverage": 1.0,
            "population": {"expected": 2, "evaluated": 2}, "conforming": 1,
            "witnesses": ["B-1"],
        }))

    def test_a_universal_claim_reports_how_many_subjects_it_skipped(self) -> None:
        self.assertIn("leaves 3 subject(s) unevaluated", _violations({
            "quantifier": "ALL", "determination": "MET", "coverage": 0.4,
            "population": {"expected": 5, "evaluated": 2}, "conforming": 2,
            "witnesses": ["B-1", "B-2"],
        }))

    def test_a_closing_proof_must_state_a_claim(self) -> None:
        report = "\n".join(proof_violations({
            "population": {"expected": 2, "evaluated": 2}, "coverage": 1.0,
            "claims": [], "result": "NOT_MET",
        }))
        self.assertIn("NOT_MET proof states no claim", report)

    def test_a_run_without_a_determination_is_refused(self) -> None:
        self.assertIn("run carries no determination", "\n".join(run_violations({"runId": "RUN-1"})))

    def test_a_run_whose_proof_is_not_an_object_is_refused(self) -> None:
        report = "\n".join(run_violations({
            "determination": {
                "quantifier": "ALL", "determination": "MET", "coverage": 1.0,
                "population": {"expected": 1, "evaluated": 1}, "conforming": 1,
                "witnesses": ["B-1"],
            },
            "proof": "a proof, honestly",
        }))
        self.assertIn("proof is present but is not an object", report)


if __name__ == "__main__":
    unittest.main()
