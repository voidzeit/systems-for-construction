import json
from pathlib import Path
import unittest

from sfc.assurance import evaluate_obligation
from sfc.io import load_obligation, load_world
from sfc.ifc import load_ifc
from sfc.models import (
    DeterminationStatus,
    Obligation,
    ProjectWorld,
    Quantifier,
    Requirement,
    WorldElement,
)


ROOT = Path(__file__).parents[1]


class AssuranceTests(unittest.TestCase):
    def test_reference_example_has_one_counterexample(self) -> None:
        obligation = load_obligation(ROOT / "examples/electrical-panel-clearance/requirement.json")
        world = load_world(ROOT / "examples/electrical-panel-clearance/project-world.json")
        determination = evaluate_obligation(obligation, world)
        self.assertEqual(determination.status, DeterminationStatus.NOT_MET)
        self.assertEqual(determination.expected_population, 18)
        self.assertEqual(determination.evaluated_population, 18)
        self.assertEqual(determination.conforming, 17)
        self.assertEqual(len(determination.counterexamples), 1)
        self.assertEqual(determination.counterexamples[0].subject, "LP-18")

    def test_missing_value_is_incomplete(self) -> None:
        obligation = Obligation(
            obligation_id="o1",
            requirement=Requirement("r1", "Clearance", "All panels have clearance"),
            quantifier=Quantifier.ALL,
            population={"kind": "panel"},
            predicate={"property": "clearance", "operator": ">=", "value": 36},
        )
        world = ProjectWorld("p1", (WorldElement("P-1", "panel", {}),))
        determination = evaluate_obligation(obligation, world)
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertEqual(determination.coverage, 0)
        self.assertEqual(determination.counterexamples, ())

    def test_any_none_and_count_semantics(self) -> None:
        elements = (
            WorldElement("A", "fixture", {"emergency": True}),
            WorldElement("B", "fixture", {"emergency": False}),
        )
        world = ProjectWorld("p", elements)
        base = dict(requirement=Requirement("r", "x", "x"), population={"kind": "fixture"}, predicate={"property": "emergency", "operator": "==", "value": True})
        self.assertEqual(evaluate_obligation(Obligation("any", quantifier=Quantifier.ANY, **base), world).status, DeterminationStatus.MET)
        self.assertEqual(evaluate_obligation(Obligation("none", quantifier=Quantifier.NONE, **base), world).status, DeterminationStatus.NOT_MET)

    def test_ifc_properties_become_world_observations(self) -> None:
        world = load_ifc(ROOT / "examples/ifc-panel-clearance/demo.ifc")
        self.assertEqual(world.project_id, "SFC-DEMO-PROJECT")
        self.assertEqual(len(world.elements), 2)
        self.assertEqual(world.metadata["units"]["length"], "m")
        self.assertEqual(
            world.elements[0].properties["WorkingClearance"],
            {"value": 1.0668, "unit": "m", "ifcType": "IFCLENGTHMEASURE", "provenance": "IFCUNITASSIGNMENT"},
        )
        self.assertEqual(world.elements[1].properties["WorkingClearance"]["value"], 0.74676)
        self.assertEqual(world.elements[0].geometry["placementRefs"], ["62"])
        self.assertEqual(world.elements[0].geometry["coordinates"], [0.0, 0.0, 0.0])
        self.assertEqual(len(world.relationships), 1)
        self.assertIn("PANEL-IFC-01", world.relationships[0]["relatedEntityIds"])
