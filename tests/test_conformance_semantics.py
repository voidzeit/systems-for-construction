"""The semantic layer of the contract, exercised from the producer's side.

Every document here is well-formed against ``spec/*.schema.json``: the field
names are right, the types are right, the enums are right. Each one is also
semantically impossible. JSON Schema cannot reject them, because each violation
is a statement about how two fields relate rather than about one field's shape.

The tests are written against dictionaries rather than SFC objects on purpose.
A correct Python producer is not the guarantee being tested; the guarantee is
that a document written by anything at all is checkable at the boundary.
"""

from __future__ import annotations

import unittest

from sfc.conformance import ConformanceError, run_violations, validate_semantics


def _determination(**overrides) -> dict:
    document = {
        "requirementId": "REQ-1",
        "obligationId": "OBL-1",
        "quantifier": "ALL",
        "population": {"expected": 2, "evaluated": 2},
        "coverage": 1.0,
        "conforming": 2,
        "witnesses": ["B-1", "B-2"],
        "counterexamples": [],
        "evidenceIds": ["E-1", "E-2"],
        "inspectedEvidenceIds": [],
        "unknowns": [],
        "determination": "MET",
    }
    document.update(overrides)
    return document


def _proof(**overrides) -> dict:
    document = {
        "requirementId": "REQ-1",
        "population": {"expected": 2, "evaluated": 2},
        "coverage": 1.0,
        "claims": [{"statement": "2 of 2 subjects satisfy the obligation", "quantifier": "ALL"}],
        "evidence": ["E-1", "E-2"],
        "inspectedEvidence": [],
        "witnesses": ["B-1", "B-2"],
        "unknowns": [],
        "result": "MET",
    }
    document.update(overrides)
    return document


def _run(**overrides) -> dict:
    document = {
        "runId": "RUN-1",
        "projectId": "P-1",
        "inputHash": "abc",
        "status": "published",
        "createdAt": "2026-01-01T00:00:00Z",
        "determination": _determination(),
        "proof": _proof(),
    }
    document.update(overrides)
    return document


def _assert_rejected(test: unittest.TestCase, kind: str, document: dict, fragment: str) -> None:
    with test.assertRaises(ConformanceError) as raised:
        validate_semantics(kind, document)
    test.assertIn(fragment, str(raised.exception))


class BaselineTests(unittest.TestCase):
    def test_the_fixtures_themselves_are_conformant(self) -> None:
        validate_semantics("determination.schema.json", _determination())
        validate_semantics("proof.schema.json", _proof())
        validate_semantics("run.schema.json", _run())

    def test_an_unknown_document_kind_is_refused_rather_than_passed(self) -> None:
        with self.assertRaises(ValueError):
            validate_semantics("obligation.schema.json", {})


class EvidenceSeparationTests(unittest.TestCase):
    """Supporting evidence and inspected evidence are different claims."""

    def test_the_same_evidence_cannot_both_support_and_be_merely_inspected(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(
                determination="INCOMPLETE",
                conforming=1,
                witnesses=["B-1"],
                population={"expected": 2, "evaluated": 1},
                coverage=0.5,
                evidenceIds=["E-1"],
                inspectedEvidenceIds=["E-1"],
                unknowns=[{"subject": "B-2", "reason": "UNRESOLVED_MEASUREMENT_UNIT", "evidenceIds": ["E-1"]}],
            ),
            "both supporting and merely inspected",
        )

    def test_a_proof_carries_the_same_separation(self) -> None:
        _assert_rejected(
            self,
            "proof.schema.json",
            _proof(evidence=["E-1"], inspectedEvidence=["E-1"],
                   unknowns=[{"subject": "B-2", "reason": "X", "evidenceIds": ["E-1"]}]),
            "both supporting and merely inspected",
        )

    def test_evidence_examined_on_an_undecided_subject_must_be_accounted_for(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(
                determination="INCOMPLETE",
                conforming=1,
                witnesses=["B-1"],
                population={"expected": 2, "evaluated": 1},
                coverage=0.5,
                evidenceIds=["E-1"],
                inspectedEvidenceIds=[],
                unknowns=[{"subject": "B-2", "reason": "MISSING_OBSERVATION", "evidenceIds": ["E-2"]}],
            ),
            "listed nowhere",
        )

    def test_inspected_evidence_must_belong_to_an_undecided_subject(self) -> None:
        # Otherwise "inspected" becomes a free-form list, and the distinction
        # from supporting evidence stops meaning anything.
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(inspectedEvidenceIds=["E-9"]),
            "belongs to no undecided subject",
        )


class PopulationTests(unittest.TestCase):
    def test_an_empty_population_cannot_state_coverage(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(
                determination="INCOMPLETE",
                population={"expected": 0, "evaluated": 0},
                coverage=1.0,
                conforming=0,
                witnesses=[],
                evidenceIds=[],
            ),
            "a fraction of nothing",
        )

    def test_coverage_must_agree_with_the_counts_it_summarises(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(
                determination="INCOMPLETE",
                population={"expected": 10, "evaluated": 2},
                coverage=1.0,
                unknowns=[{"subject": "B-3", "reason": "MISSING_OBSERVATION"}],
            ),
            "does not describe 2 of 10",
        )

    def test_absence_is_never_compliance(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(
                population={"expected": 0, "evaluated": 0},
                coverage=None,
                conforming=0,
                witnesses=[],
                evidenceIds=[],
            ),
            "absence is not compliance",
        )

    def test_not_applicable_needs_evidence_of_non_applicability(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(
                determination="NOT_APPLICABLE",
                population={"expected": 0, "evaluated": 0},
                coverage=None,
                conforming=0,
                witnesses=[],
                evidenceIds=[],
            ),
            "without evidence that the requirement does not apply",
        )


class QuantifierTests(unittest.TestCase):
    def test_a_universal_claim_cannot_close_over_a_partial_population(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(population={"expected": 5, "evaluated": 2}, coverage=0.4, conforming=2),
            "unevaluated",
        )

    def test_an_existential_claim_must_name_its_witness(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(quantifier="ANY", conforming=0, witnesses=[]),
            "names no witness",
        )

    def test_an_existential_claim_survives_a_partial_population(self) -> None:
        # The counterpart of the universal case: one witness settles it.
        validate_semantics("determination.schema.json", _determination(
            quantifier="ANY",
            population={"expected": 5, "evaluated": 1},
            coverage=0.2,
            conforming=1,
            witnesses=["B-1"],
            evidenceIds=["E-1"],
            inspectedEvidenceIds=["E-2"],
            unknowns=[{"subject": "B-2", "reason": "MISSING_OBSERVATION", "evidenceIds": ["E-2"]}],
        ))

    def test_a_violated_universal_claim_must_carry_a_counterexample(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(determination="NOT_MET", conforming=1, witnesses=["B-1"], counterexamples=[]),
            "carries no counterexample",
        )

    def test_a_violated_prohibition_must_name_the_offending_subject(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(quantifier="NONE", determination="NOT_MET", conforming=0, witnesses=[]),
            "names no subject that satisfies the predicate",
        )

    def test_a_subject_cannot_hold_two_roles(self) -> None:
        _assert_rejected(
            self,
            "determination.schema.json",
            _determination(counterexamples=[{"subject": "B-1"}], determination="NOT_MET"),
            "both satisfies and fails the predicate",
        )


class RunLinkageTests(unittest.TestCase):
    """A run's proof has to be a proof of that run's determination."""

    def test_a_proof_about_another_requirement_is_refused(self) -> None:
        _assert_rejected(self, "run.schema.json", _run(proof=_proof(requirementId="REQ-9")),
                         "proof requirementId does not describe this determination")

    def test_a_proof_stating_another_result_is_refused(self) -> None:
        _assert_rejected(self, "run.schema.json", _run(proof=_proof(result="NOT_MET")),
                         "proof result does not describe this determination")

    def test_a_proof_over_another_population_is_refused(self) -> None:
        _assert_rejected(self, "run.schema.json",
                         _run(proof=_proof(population={"expected": 9, "evaluated": 9}, coverage=1.0)),
                         "proof population does not describe this determination")

    def test_a_proof_citing_other_evidence_is_refused(self) -> None:
        _assert_rejected(self, "run.schema.json", _run(proof=_proof(evidence=["E-9"])),
                         "proof evidence does not describe this determination")

    def test_a_run_may_carry_no_proof_at_all(self) -> None:
        validate_semantics("run.schema.json", _run(proof=None))

    def test_a_broken_determination_is_reported_through_the_run(self) -> None:
        broken = _run(determination=_determination(coverage=0.5), proof=_proof(coverage=0.5))
        violations = list(run_violations(broken))
        self.assertTrue(any(violation.startswith("determination:") for violation in violations))
        self.assertTrue(any(violation.startswith("proof:") for violation in violations))

    def test_every_violation_is_reported_not_just_the_first(self) -> None:
        with self.assertRaises(ConformanceError) as raised:
            validate_semantics("determination.schema.json", _determination(
                quantifier="ANY",
                conforming=0,
                witnesses=[],
                coverage=0.5,
                inspectedEvidenceIds=["E-1"],
            ))
        self.assertGreater(len(raised.exception.violations), 1)


if __name__ == "__main__":
    unittest.main()
