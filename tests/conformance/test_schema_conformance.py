"""Every artifact SFC publishes is validated against its portable schema.

Without these tests the documents in spec/ are parallel documentation: an
adapter could write a run the runtime accepts and the schema rejects, and
nothing would notice. This suite makes spec/ an executable boundary.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from sfc.assurance import evaluate_obligation
from sfc.control_plane import ControlPlane
from sfc.events import Event, EventLog
from sfc.governance import Review, ReviewDecision, ValueRecord
from sfc.ifc import load_ifc
from sfc.investigation import investigate_and_publish
from sfc.io import load_obligation, load_world
from sfc.lifecycle import ObligationStatus, ValueStatus, WorkPackage, WorkPackageStatus
from sfc.models import Determination, Evidence, Obligation, ProjectWorld
from sfc.proofs import Proof
from sfc.runtime import RunStore

from . import schemas

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/electrical-panel-clearance"
IFC_EXAMPLE = ROOT / "examples/ifc-panel-clearance"


class SchemaHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        schemas.requires_schemas(self)

    def test_every_schema_is_itself_valid(self) -> None:
        paths = schemas.schema_paths()
        self.assertTrue(paths, "no schemas found in spec/")
        for path in paths:
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                schemas.Draft202012Validator.check_schema(schema)

    def test_every_schema_declares_an_identity(self) -> None:
        for path in schemas.schema_paths():
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("$id", schema)
                self.assertTrue(schema["$id"].endswith(path.name))
                self.assertEqual(schema.get("$schema"), "https://json-schema.org/draft/2020-12/schema")

    def test_cross_file_references_resolve(self) -> None:
        # run.schema.json refers to determination.schema.json by relative URI.
        run_validator = schemas.validator("run.schema.json")
        reference = run_validator.schema["properties"]["determination"]["$ref"]
        self.assertEqual(reference, "determination.schema.json")
        resolved = run_validator._resolver.lookup(reference)
        self.assertEqual(resolved.contents["title"], "SFC Determination")


class ExampleConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        schemas.requires_schemas(self)

    def test_example_obligations_conform(self) -> None:
        for path in sorted(ROOT.glob("examples/*/requirement.json")):
            with self.subTest(example=path.parent.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                schemas.assert_valid(self, "obligation.schema.json", document)

    def test_obligations_round_trip(self) -> None:
        for path in sorted(ROOT.glob("examples/*/requirement.json")):
            with self.subTest(example=path.parent.name):
                schemas.assert_roundtrip(self, "obligation.schema.json", load_obligation(path), Obligation.from_dict)

    def test_compiled_obligation_conforms(self) -> None:
        from sfc.requirements import compile_requirement

        obligation = compile_requirement("Every electrical panel must maintain 36 inches of working clearance")
        schemas.assert_roundtrip(self, "obligation.schema.json", obligation, Obligation.from_dict)


class DeterminationConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        schemas.requires_schemas(self)
        self.obligation = load_obligation(EXAMPLE / "requirement.json")
        self.world = load_world(EXAMPLE / "project-world.json")

    def test_determination_conforms_and_round_trips(self) -> None:
        determination = evaluate_obligation(self.obligation, self.world)
        self.assertEqual(determination.status.value, "NOT_MET")
        schemas.assert_roundtrip(self, "determination.schema.json", determination, Determination.from_dict)

    def test_proof_conforms(self) -> None:
        proof = Proof.from_determination(evaluate_obligation(self.obligation, self.world))
        schemas.assert_valid(self, "proof.schema.json", proof.to_dict())

    def test_empty_population_determination_conforms(self) -> None:
        obligation = Obligation.from_dict({
            **self.obligation.to_dict(),
            "population": {"kind": "nothing_matches_this", "minimumExpected": 1},
        })
        determination = evaluate_obligation(obligation, self.world)
        self.assertEqual(determination.status.value, "INCOMPLETE")
        self.assertIsNone(determination.to_dict()["coverage"])
        schemas.assert_roundtrip(self, "determination.schema.json", determination, Determination.from_dict)

    def test_not_applicable_determination_conforms(self) -> None:
        obligation = Obligation.from_dict({
            **self.obligation.to_dict(),
            "population": {
                "kind": "nothing_matches_this",
                "applicability": {"applicable": False, "evidenceIds": ["E-SCOPE-1"], "basis": "out of scope"},
            },
        })
        determination = evaluate_obligation(obligation, self.world)
        self.assertEqual(determination.status.value, "NOT_APPLICABLE")
        schemas.assert_roundtrip(self, "determination.schema.json", determination, Determination.from_dict)

    def test_determination_with_a_unit_assumption_conforms(self) -> None:
        obligation = Obligation.from_dict({
            **self.obligation.to_dict(),
            "predicate": {"property": "working_clearance", "operator": ">=", "value": 36, "unit": "in"},
            "measurement": {"assumeObservedUnit": "in", "assumptionBasis": "legacy vocabulary mapping"},
        })
        # A world whose observations carry no unit, so the policy applies.
        stripped = json.loads(json.dumps(self.world.to_dict()))
        for element in stripped["elements"]:
            element["properties"]["working_clearance"] = element["properties"]["working_clearance"]["value"]
        determination = evaluate_obligation(obligation, ProjectWorld.from_dict(stripped))
        self.assertTrue(determination.assumptions)
        schemas.assert_roundtrip(self, "determination.schema.json", determination, Determination.from_dict)


class RunConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        schemas.requires_schemas(self)

    def test_published_run_conforms(self) -> None:
        from sfc.runtime import create_run

        obligation = load_obligation(EXAMPLE / "requirement.json")
        world = load_world(EXAMPLE / "project-world.json")
        with TemporaryDirectory() as directory:
            store = RunStore(directory)
            frozen = store.freeze(world, obligation)
            run = create_run(world, frozen, evaluate_obligation(obligation, world))
            path = store.publish(run)
            schemas.assert_valid(self, "run.schema.json", run.to_dict())
            # The artifact on disk is the contract, not just the in-memory object.
            schemas.assert_valid(self, "run.schema.json", json.loads(path.read_text(encoding="utf-8")))
            schemas.assert_valid(self, "run.schema.json", store.load_canonical())

    def test_investigation_run_evidence_and_proof_conform(self) -> None:
        world = load_ifc(IFC_EXAMPLE / "demo.ifc")
        with TemporaryDirectory() as directory:
            publication = investigate_and_publish(
                world,
                "Every electrical distribution board must maintain 36 inches of working clearance",
                store=RunStore(directory),
            )
        schemas.assert_valid(self, "run.schema.json", publication.run.to_dict())
        schemas.assert_valid(self, "proof.schema.json", publication.proof.to_dict())
        self.assertTrue(publication.admitted_evidence)
        for evidence in publication.admitted_evidence:
            with self.subTest(evidence=evidence.evidence_id):
                schemas.assert_roundtrip(self, "evidence.schema.json", evidence, Evidence.from_dict)
                self.assertEqual(evidence.measurement["normalizedUnit"], "in")


class ControlPlaneConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        schemas.requires_schemas(self)

    def test_review_value_and_work_package_conform(self) -> None:
        review = Review("REV-1", "OBL-1", ReviewDecision.ACCEPTED, "reviewer-1", reason="checked on site")
        schemas.assert_roundtrip(self, "review.schema.json", review, Review.from_dict)

        value = ValueRecord("VAL-1", "WP-1", ValueStatus.BUDGETED, 1000.0, "USD")
        schemas.assert_roundtrip(self, "value.schema.json", value, ValueRecord.from_dict)

        package = WorkPackage("WP-1", "Install boards", ("OBL-1",), WorkPackageStatus.PLANNED)
        schemas.assert_roundtrip(self, "work-package.schema.json", package, WorkPackage.from_dict)

    def test_every_emitted_event_conforms(self) -> None:
        with TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "events.jsonl")
            plane = ControlPlane(event_log=log)
            plane.register_obligation("OBL-1")
            plane.advance_obligation("OBL-1", ObligationStatus.CLASSIFIED, "actor-1")
            plane.add_work_package(WorkPackage("WP-1", "Install boards", ("OBL-1",)))
            plane.advance_work_package("WP-1", WorkPackageStatus.IN_PROGRESS, "actor-1")
            plane.add_review(Review("REV-1", "OBL-1", ReviewDecision.ACCEPTED, "reviewer-1"))
            plane.add_value(ValueRecord("VAL-1", "WP-1"))
            plane.advance_value("VAL-1", ValueStatus.BUDGETED, actor_id="actor-1")
            events = log.read()
        self.assertEqual(len(events), 7)
        for event in events:
            with self.subTest(event=event["eventType"]):
                schemas.assert_valid(self, "event.schema.json", event)

    def test_event_round_trips(self) -> None:
        event = Event("determination.produced", "OBL-1", {"status": "NOT_MET"}, actor_id="actor-1")
        schemas.assert_valid(self, "event.schema.json", event.to_dict())


class FixtureDirectionTests(unittest.TestCase):
    """Schema fixture -> python object -> JSON -> schema, the other direction."""

    def setUp(self) -> None:
        schemas.requires_schemas(self)

    def test_evidence_fixture_loads_and_re_validates(self) -> None:
        fixture = {
            "evidenceId": "E-1",
            "sourceId": "ifc:abc",
            "sourceType": "model_element",
            "locator": {"elementId": "PANEL-IFC-01", "property": "WorkingClearance"},
            "observedValue": {"value": 0.74676, "unit": "m"},
            "authority": 0.8,
            "confidence": 1.0,
            "provenance": ["project-world"],
            "measurement": {
                "rawValue": 0.74676,
                "rawUnit": "m",
                "normalizedValue": 29.4,
                "normalizedUnit": "in",
                "dimension": "length",
                "conversion": 39.37007874015748,
                "source": "IFCUNITASSIGNMENT",
            },
        }
        schemas.assert_valid(self, "evidence.schema.json", fixture)
        schemas.assert_valid(self, "evidence.schema.json", Evidence.from_dict(fixture).to_dict())

    def test_an_unknown_field_is_rejected(self) -> None:
        fixture = {"reviewId": "REV-1", "targetId": "OBL-1", "decision": "accepted",
                   "reviewerId": "r1", "reviewedAt": "2026-01-01T00:00:00Z", "unexpected": True}
        self.assertFalse(schemas.validator("review.schema.json").is_valid(fixture))

    def test_a_vacuous_determination_is_rejected_by_the_schema_status_enum(self) -> None:
        fixture = {"requirementId": "R", "obligationId": "O", "quantifier": "ALL",
                   "population": {"expected": 0, "evaluated": 0}, "coverage": None,
                   "conforming": 0, "determination": "VACUOUS"}
        self.assertFalse(schemas.validator("determination.schema.json").is_valid(fixture))


if __name__ == "__main__":
    unittest.main()
