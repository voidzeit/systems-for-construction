"""Each quantifier closes on its own terms, and publication accepts all four.

The evaluator has always applied existential and universal logic correctly, but
``validate_determination`` held every quantifier to the universal rule: full
coverage, no counterexamples, no unknowns. That made a correct ANY or NONE
determination unpublishable, because the publication boundary rejected exactly
the shapes those quantifiers are supposed to produce.

    ALL     falls to one counterexample, closes only on the whole population
    ANY     closes on one witness, survives undecided and failing subjects
    NONE    closes on the whole population with no witness
    COUNT   closes on the whole population within its bounds
"""

from __future__ import annotations

from dataclasses import replace
from tempfile import TemporaryDirectory
import unittest

from sfc.assurance import AssuranceError, evaluate_obligation, validate_determination
from sfc.models import DeterminationStatus, Obligation, ProjectWorld, Quantifier, Requirement, WorldElement
from sfc.runtime import RunStore, create_run

PASSES = {"value": 1.0, "unit": "m"}      # 39.37 in, satisfies >= 36 in
FAILS = {"value": 0.5, "unit": "m"}       # 19.69 in, does not
UNDECIDABLE = 29.4                        # no unit, so never compared


def _obligation(quantifier: Quantifier, **predicate) -> Obligation:
    return Obligation(
        obligation_id="OBL-1",
        requirement=Requirement("REQ-1", "Spacing", "Subjects must maintain spacing"),
        quantifier=quantifier,
        population={"kind": "board"},
        predicate={"property": "spacing", "operator": ">=", "value": 36, "unit": "in", **predicate},
    )


def _world(*values) -> ProjectWorld:
    return ProjectWorld("p", tuple(
        WorldElement(f"B-{index}", "board", {"spacing": value}, {"spacing": (f"E-{index}",)})
        for index, value in enumerate(values)
    ))


def _decide(quantifier: Quantifier, *values, **predicate):
    """Evaluate and assert the result is publishable, which is the point."""
    determination = evaluate_obligation(_obligation(quantifier, **predicate), _world(*values))
    validate_determination(determination)
    return determination


class ExistentialClosureTests(unittest.TestCase):
    def test_any_closes_on_one_witness_despite_an_undecided_subject(self) -> None:
        determination = _decide(Quantifier.ANY, PASSES, UNDECIDABLE)
        self.assertEqual(determination.status, DeterminationStatus.MET)
        self.assertEqual(determination.witnesses, ("B-0",))
        self.assertEqual(determination.coverage, 0.5)
        self.assertTrue(determination.unknowns)

    def test_any_closes_on_one_witness_despite_a_failing_subject(self) -> None:
        determination = _decide(Quantifier.ANY, PASSES, FAILS)
        self.assertEqual(determination.status, DeterminationStatus.MET)
        self.assertEqual(determination.witnesses, ("B-0",))
        self.assertEqual(len(determination.counterexamples), 1)

    def test_any_is_only_violated_once_the_whole_population_was_looked_at(self) -> None:
        settled = _decide(Quantifier.ANY, FAILS, FAILS)
        self.assertEqual(settled.status, DeterminationStatus.NOT_MET)
        self.assertEqual(settled.witnesses, ())

        still_open = _decide(Quantifier.ANY, FAILS, UNDECIDABLE)
        self.assertEqual(still_open.status, DeterminationStatus.INCOMPLETE)

    def test_a_met_existential_claim_must_name_its_witness(self) -> None:
        determination = _decide(Quantifier.ANY, PASSES, FAILS)
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(replace(determination, witnesses=()))
        self.assertIn("must name the witness", str(raised.exception))


class UniversalClosureTests(unittest.TestCase):
    def test_all_falls_to_a_single_counterexample_even_with_unknowns(self) -> None:
        determination = _decide(Quantifier.ALL, FAILS, UNDECIDABLE)
        self.assertEqual(determination.status, DeterminationStatus.NOT_MET)
        self.assertEqual(len(determination.counterexamples), 1)

    def test_all_does_not_close_as_met_on_a_partially_evaluated_population(self) -> None:
        determination = _decide(Quantifier.ALL, PASSES, UNDECIDABLE)
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(replace(determination, status=DeterminationStatus.MET))
        self.assertIn("complete population coverage", str(raised.exception))

    def test_none_closes_when_no_subject_satisfies_the_predicate(self) -> None:
        determination = _decide(Quantifier.NONE, FAILS, FAILS)
        self.assertEqual(determination.status, DeterminationStatus.MET)
        self.assertEqual(determination.witnesses, ())
        # Under a prohibition, failing the predicate is what compliance is.
        self.assertEqual(len(determination.counterexamples), 2)

    def test_none_names_the_subject_that_violated_the_prohibition(self) -> None:
        determination = _decide(Quantifier.NONE, PASSES, FAILS)
        self.assertEqual(determination.status, DeterminationStatus.NOT_MET)
        self.assertEqual(determination.witnesses, ("B-0",))
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(replace(determination, witnesses=()))
        self.assertIn("must name the subject", str(raised.exception))

    def test_count_closes_within_its_bounds_over_the_whole_population(self) -> None:
        determination = _decide(Quantifier.COUNT, PASSES, PASSES, minimum=2)
        self.assertEqual(determination.status, DeterminationStatus.MET)
        self.assertEqual(determination.witnesses, ("B-0", "B-1"))


class SubjectRoleTests(unittest.TestCase):
    def test_a_subject_cannot_both_satisfy_and_fail_the_predicate(self) -> None:
        determination = _decide(Quantifier.ANY, PASSES, FAILS)
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(replace(determination, witnesses=("B-0", "B-1"), conforming=2))
        self.assertIn("both satisfy and fail", str(raised.exception))

    def test_a_witness_cannot_also_be_undecided(self) -> None:
        determination = _decide(Quantifier.ANY, PASSES, UNDECIDABLE)
        # Counts kept consistent, so only the subject roles are in conflict:
        # B-1 is claimed as a witness while still listed as undecided.
        forged = replace(
            determination,
            witnesses=("B-0", "B-1"),
            conforming=2,
            evaluated_population=2,
            coverage=1.0,
        )
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(forged)
        self.assertIn("both a witness and undecided", str(raised.exception))

    def test_witnesses_cannot_outnumber_the_conforming_count(self) -> None:
        determination = _decide(Quantifier.COUNT, PASSES, PASSES, minimum=2)
        with self.assertRaises(AssuranceError) as raised:
            validate_determination(replace(determination, conforming=1))
        self.assertIn("more witnesses", str(raised.exception))


class PublicationTests(unittest.TestCase):
    def test_every_quantifier_survives_the_publication_boundary(self) -> None:
        cases = {
            Quantifier.ALL: ((PASSES, PASSES), {}),
            Quantifier.ANY: ((PASSES, UNDECIDABLE), {}),
            Quantifier.NONE: ((FAILS, FAILS), {}),
            Quantifier.COUNT: ((PASSES, PASSES), {"minimum": 2}),
        }
        for quantifier, (values, predicate) in cases.items():
            with self.subTest(quantifier=quantifier.value):
                obligation = _obligation(quantifier, **predicate)
                world = _world(*values)
                determination = evaluate_obligation(obligation, world)
                self.assertEqual(determination.status, DeterminationStatus.MET)
                with TemporaryDirectory() as directory:
                    store = RunStore(directory)
                    frozen = store.freeze(world, obligation)
                    # publish() applies the invariants, so an unpublishable MET
                    # raises here rather than reaching disk.
                    store.publish(create_run(world, frozen, determination))
                    self.assertEqual(store.load_canonical()["determination"]["determination"], "MET")


if __name__ == "__main__":
    unittest.main()
