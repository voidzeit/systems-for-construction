import unittest

from sfc.assurance import evaluate_obligation, observe_measurement
from sfc.models import DeterminationReason, DeterminationStatus, Obligation, ProjectWorld, Quantifier, Requirement, WorldElement
from sfc.quantities import (
    Conversion,
    Dimension,
    IncompatibleDimensionError,
    Quantity,
    UnknownUnitError,
    UnresolvedUnitError,
    compare_values,
    resolve_unit,
)
from sfc.requirements import RequirementCompilationError, compile_requirement


class UnitResolutionTests(unittest.TestCase):
    def test_spellings_resolve_to_one_symbol(self) -> None:
        for token in ("in", "inch", "inches", "IN", " Inches ", '"'):
            self.assertEqual(resolve_unit(token), "in", token)
        for token in ("m", "metre", "meters", "METRE"):
            self.assertEqual(resolve_unit(token), "m", token)
        for token in ("mm", "millimetre", "MILLIMETERS"):
            self.assertEqual(resolve_unit(token), "mm", token)

    def test_absent_unit_is_absent_not_dimensionless_default(self) -> None:
        self.assertIsNone(resolve_unit(None))
        self.assertIsNone(resolve_unit(""))
        self.assertIsNone(resolve_unit("  "))

    def test_unrecognized_unit_raises_instead_of_degrading(self) -> None:
        with self.assertRaises(UnknownUnitError):
            resolve_unit("psi")

    def test_superscripts_and_exponents(self) -> None:
        self.assertEqual(resolve_unit("m²"), "m2")
        self.assertEqual(resolve_unit("m^3"), "m3")
        self.assertEqual(resolve_unit("square feet"), "ft2")


class QuantityTests(unittest.TestCase):
    def test_dimension_follows_the_unit(self) -> None:
        self.assertIs(Quantity(1.0, "mm").dimension, Dimension.LENGTH)
        self.assertIs(Quantity(1.0, "kg").dimension, Dimension.MASS)
        self.assertIsNone(Quantity(1.0).dimension)

    def test_parse_accepts_scalars_mappings_and_strings(self) -> None:
        self.assertEqual(Quantity.parse(36, "in"), Quantity(36.0, "in"))
        self.assertEqual(Quantity.parse({"value": 0.9144, "unit": "m"}), Quantity(0.9144, "m"))
        self.assertEqual(Quantity.parse("914.4 mm"), Quantity(914.4, "mm"))

    def test_parse_returns_none_for_non_measurements(self) -> None:
        for value in (True, False, None, "emergency", {"other": 1}):
            self.assertIsNone(Quantity.parse(value), value)

    def test_conversion_is_deterministic(self) -> None:
        self.assertAlmostEqual(Quantity(36, "in").to("m").value, 0.9144, places=12)
        self.assertAlmostEqual(Quantity(0.74676, "m").to("in").value, 29.4, places=9)
        self.assertAlmostEqual(Quantity(1, "ft").to("in").value, 12.0, places=12)

    def test_conversion_across_dimensions_is_refused(self) -> None:
        with self.assertRaises(IncompatibleDimensionError):
            Quantity(1, "kg").to("m")

    def test_conversion_from_an_undeclared_unit_is_refused(self) -> None:
        with self.assertRaises(UnresolvedUnitError):
            Quantity(29.4).to("in")

    def test_audit_records_both_sides_of_the_conversion(self) -> None:
        audit = Conversion(Quantity(0.74676, "m", "IFCUNITASSIGNMENT"), Quantity(29.4, "in")).to_dict()
        self.assertEqual(audit["rawValue"], 0.74676)
        self.assertEqual(audit["rawUnit"], "m")
        self.assertEqual(audit["normalizedUnit"], "in")
        self.assertEqual(audit["source"], "IFCUNITASSIGNMENT")


class ToleranceTests(unittest.TestCase):
    def test_a_converted_boundary_value_still_satisfies_the_requirement(self) -> None:
        # 12 in is exactly 0.3048 m, but the binary round trip lands just above
        # it. A strict comparison would report a violation that does not exist.
        normalized = Quantity(0.3048, "m").to("in").value
        self.assertNotEqual(normalized, 12.0)
        self.assertTrue(compare_values(normalized, ">=", 12))
        self.assertTrue(compare_values(normalized, "<=", 12))
        self.assertTrue(compare_values(normalized, "==", 12))
        self.assertFalse(compare_values(normalized, ">", 12))
        self.assertFalse(compare_values(normalized, "<", 12))

    def test_tolerance_does_not_erase_a_real_difference(self) -> None:
        self.assertFalse(compare_values(35.9, ">=", 36))
        self.assertTrue(compare_values(35.9, "<", 36))
        self.assertFalse(compare_values(35.999, "==", 36))

    def test_a_boundary_requirement_is_evaluated_at_the_boundary(self) -> None:
        obligation = _obligation()
        determination = evaluate_obligation(obligation, _world({"value": 0.9144, "unit": "m"}))
        self.assertEqual(determination.status, DeterminationStatus.MET)


def _obligation(unit: str | None = "in", measurement: dict | None = None) -> Obligation:
    predicate = {"property": "working_clearance", "operator": ">=", "value": 36}
    if unit is not None:
        predicate["unit"] = unit
    return Obligation(
        obligation_id="OBL-1",
        requirement=Requirement("REQ-1", "Clearance", "Every board must maintain clearance"),
        quantifier=Quantifier.ALL,
        population={"kind": "board"},
        predicate=predicate,
        measurement=measurement or {},
    )


def _world(value) -> ProjectWorld:
    return ProjectWorld("p", (WorldElement("B-1", "board", {"working_clearance": value}, {"working_clearance": ("E-1",)}),))


class MeasurementEvaluationTests(unittest.TestCase):
    def test_metric_observation_meets_an_imperial_requirement(self) -> None:
        determination = evaluate_obligation(_obligation(), _world({"value": 1.0668, "unit": "m"}))
        self.assertEqual(determination.status, DeterminationStatus.MET)

    def test_metric_observation_fails_an_imperial_requirement(self) -> None:
        determination = evaluate_obligation(_obligation(), _world({"value": 0.74676, "unit": "m"}))
        self.assertEqual(determination.status, DeterminationStatus.NOT_MET)
        audit = determination.counterexamples[0].measurement
        self.assertEqual(audit["rawUnit"], "m")
        self.assertEqual(audit["normalizedUnit"], "in")
        self.assertAlmostEqual(audit["normalizedValue"], 29.4, places=9)

    def test_an_unresolved_unit_is_never_compared_numerically(self) -> None:
        determination = evaluate_obligation(_obligation(), _world(29.4))
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertIn(DeterminationReason.UNRESOLVED_MEASUREMENT_UNIT.value, determination.reasons)
        self.assertEqual(determination.counterexamples, ())
        self.assertEqual(determination.evaluated_population, 0)

    def test_an_unresolved_unit_does_not_cite_evidence(self) -> None:
        determination = evaluate_obligation(_obligation(), _world(29.4))
        self.assertEqual(determination.evidence_ids, ())

    def test_incompatible_dimensions_are_refused(self) -> None:
        determination = evaluate_obligation(_obligation(), _world({"value": 5, "unit": "kg"}))
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertIn(DeterminationReason.INCOMPATIBLE_MEASUREMENT_DIMENSION.value, determination.reasons)

    def test_two_dimensionless_values_still_compare(self) -> None:
        determination = evaluate_obligation(_obligation(unit=None), _world(42))
        self.assertEqual(determination.status, DeterminationStatus.MET)

    def test_non_measurements_compare_directly(self) -> None:
        obligation = Obligation(
            obligation_id="OBL-2",
            requirement=Requirement("REQ-2", "Emergency", "Every board is an emergency board"),
            quantifier=Quantifier.ALL,
            population={"kind": "board"},
            predicate={"property": "emergency", "operator": "==", "value": True},
        )
        world = ProjectWorld("p", (WorldElement("B-1", "board", {"emergency": True}),))
        self.assertEqual(evaluate_obligation(obligation, world).status, DeterminationStatus.MET)


class AssumptionTests(unittest.TestCase):
    POLICY = {"assumeObservedUnit": "in", "assumptionBasis": "legacy vocabulary mapping"}

    def test_an_assumption_is_only_permitted_when_declared(self) -> None:
        without = evaluate_obligation(_obligation(), _world(29.4))
        self.assertEqual(without.status, DeterminationStatus.INCOMPLETE)
        with_policy = evaluate_obligation(_obligation(measurement=self.POLICY), _world(29.4))
        self.assertEqual(with_policy.status, DeterminationStatus.NOT_MET)

    def test_a_permitted_assumption_is_recorded(self) -> None:
        determination = evaluate_obligation(_obligation(measurement=self.POLICY), _world(29.4))
        self.assertEqual(determination.assumptions, ({
            "kind": "unit_assumption",
            "property": "working_clearance",
            "assumedUnit": "in",
            "basis": "legacy vocabulary mapping",
        },))
        self.assertEqual(determination.counterexamples[0].measurement["source"], "assumed")

    def test_a_resolved_unit_is_evidence_and_not_an_assumption(self) -> None:
        determination = evaluate_obligation(_obligation(measurement=self.POLICY), _world({"value": 0.74676, "unit": "m"}))
        self.assertEqual(determination.assumptions, ())
        self.assertEqual(determination.counterexamples[0].measurement["source"], None)


class CompilerUnitTests(unittest.TestCase):
    def test_the_captured_unit_reaches_the_predicate(self) -> None:
        imperial = compile_requirement("Every electrical panel must maintain 36 inches of working clearance")
        metric = compile_requirement("Every electrical panel must maintain 36 mm of working clearance")
        self.assertEqual(imperial.predicate["unit"], "in")
        self.assertEqual(metric.predicate["unit"], "mm")
        self.assertNotEqual(imperial.predicate, metric.predicate)

    def test_the_unit_is_not_folded_into_the_property_name(self) -> None:
        obligation = compile_requirement("Every electrical panel must maintain 36 inches of working clearance")
        self.assertEqual(obligation.predicate["property"], "working_clearance")

    def test_a_declared_minimum_population_is_compiled(self) -> None:
        obligation = compile_requirement("Every electrical panel must maintain 36 inches of working clearance")
        self.assertEqual(obligation.population["minimumExpected"], 1)

    def test_an_unrecognized_unit_is_refused(self) -> None:
        with self.assertRaises(RequirementCompilationError):
            compile_requirement("Every panel must have pressure >= 36 psi")


class ObserveMeasurementTests(unittest.TestCase):
    def test_audit_is_produced_for_a_comparable_observation(self) -> None:
        audit = observe_measurement({"value": 0.74676, "unit": "m"}, _obligation())
        self.assertEqual(audit["normalizedUnit"], "in")

    def test_no_audit_when_the_units_cannot_be_reconciled(self) -> None:
        self.assertIsNone(observe_measurement(29.4, _obligation()))
        self.assertIsNone(observe_measurement("not a measurement", _obligation()))


if __name__ == "__main__":
    unittest.main()
