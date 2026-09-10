"""The SFC release gate: eleven claims, each asserted end to end.

Each claim below is covered in depth by a focused suite. This file exists so
the set can be read and run as one statement of what SFC guarantees, rather
than reconstructed from a test tree.

    EMPTY POPULATION          never MET, and never covered, without evidence
    QUANTIFIERS               each closes on its own terms, and publishes
    UNKNOWN UNIT              never numerically compared
    CONVERTIBLE UNITS         deterministically normalized
    INCOMPATIBLE DIMENSIONS   comparison rejected
    SCHEMA DRIFT              detected
    PROOF AND RUN             one contract, and they must agree
    AEC VOCABULARY            injected, not built into the kernel
    CLI                       behaves as an installed user sees it
    LOCAL-PRIVATE             enforced by property, not by name
    PUBLISHED RUN             every invariant and the schema hold
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest

from sfc.assurance import AssuranceError, evaluate_obligation, validate_determination
from sfc.cli import main
from sfc.conformance import ConformanceError, validate_semantics
from sfc.gateway import DataResidency, ExecutionScope, GatewayPolicy, GatewayRoute, build_default_gateway
from sfc.io import load_obligation, load_world, read_json
from sfc.models import DeterminationReason, DeterminationStatus, Obligation, ProjectWorld, Quantifier, Requirement, WorldElement
from sfc.proofs import Proof
from sfc.quantities import Quantity
from sfc.runtime import RunStore, create_run
from sfc.vocabulary import Vocabulary

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples/electrical-panel-clearance"

BOARD = dict(
    requirement=Requirement("REQ-1", "Clearance", "Every board must maintain clearance"),
    quantifier=Quantifier.ALL,
    predicate={"property": "working_clearance", "operator": ">=", "value": 36, "unit": "in"},
)


def _world(value) -> ProjectWorld:
    return ProjectWorld("p", (WorldElement("B-1", "board", {"working_clearance": value}, {"working_clearance": ("E-1",)}),))


class ReleaseGate(unittest.TestCase):
    maxDiff = None

    def test_empty_population_never_met_without_evidenced_applicability(self) -> None:
        unresolved = evaluate_obligation(Obligation("O", population={"kind": "board"}, **BOARD), ProjectWorld("p", ()))
        self.assertEqual(unresolved.status, DeterminationStatus.INCOMPLETE)
        self.assertIsNone(unresolved.coverage)

        asserted = evaluate_obligation(
            Obligation("O", population={"kind": "board", "applicability": {"applicable": False}}, **BOARD),
            ProjectWorld("p", ()),
        )
        self.assertEqual(asserted.status, DeterminationStatus.INCOMPLETE)

        evidenced = evaluate_obligation(
            Obligation("O", population={"kind": "board", "applicability": {"applicable": False, "evidenceIds": ["E-SCOPE"]}}, **BOARD),
            ProjectWorld("p", ()),
        )
        self.assertEqual(evidenced.status, DeterminationStatus.NOT_APPLICABLE)
        self.assertNotEqual(evidenced.status, DeterminationStatus.MET)

        # And the invariant holds at the publication boundary, not just here.
        with self.assertRaises(AssuranceError):
            validate_determination(_met_on_nothing())
        # Nor may a document claim it covered a population it never established.
        with self.assertRaises(AssuranceError):
            validate_determination(_evaluated_all_of_nothing())

    def test_each_quantifier_closes_on_its_own_terms(self) -> None:
        existential = Obligation("O", population={"kind": "board"}, **{**BOARD, "quantifier": Quantifier.ANY})
        world = ProjectWorld("p", (
            WorldElement("B-1", "board", {"working_clearance": {"value": 1.0, "unit": "m"}}, {"working_clearance": ("E-1",)}),
            WorldElement("B-2", "board", {"working_clearance": 29.4}, {"working_clearance": ("E-2",)}),
        ))
        witnessed = evaluate_obligation(existential, world)
        # One witness settles an existential claim; the undecided subject does
        # not refute it, and the publication boundary agrees.
        self.assertEqual(witnessed.status, DeterminationStatus.MET)
        self.assertEqual(witnessed.witnesses, ("B-1",))
        self.assertEqual(witnessed.coverage, 0.5)
        validate_determination(witnessed)

        universal = evaluate_obligation(Obligation("O", population={"kind": "board"}, **BOARD), world)
        # The same partial coverage leaves a universal claim open.
        self.assertEqual(universal.status, DeterminationStatus.INCOMPLETE)

    def test_unknown_unit_is_never_numerically_compared(self) -> None:
        determination = evaluate_obligation(Obligation("O", population={"kind": "board"}, **BOARD), _world(29.4))
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertIn(DeterminationReason.UNRESOLVED_MEASUREMENT_UNIT.value, determination.reasons)
        self.assertEqual(determination.counterexamples, ())
        self.assertEqual(determination.evaluated_population, 0)
        self.assertEqual(determination.evidence_ids, ())

    def test_convertible_units_are_deterministically_normalized(self) -> None:
        determination = evaluate_obligation(Obligation("O", population={"kind": "board"}, **BOARD), _world({"value": 0.74676, "unit": "m"}))
        self.assertEqual(determination.status, DeterminationStatus.NOT_MET)
        audit = determination.counterexamples[0].measurement
        self.assertEqual((audit["rawValue"], audit["rawUnit"]), (0.74676, "m"))
        self.assertEqual(audit["normalizedUnit"], "in")
        self.assertAlmostEqual(audit["normalizedValue"], 29.4, places=9)
        self.assertAlmostEqual(Quantity(914.4, "mm").to("in").value, 36.0, places=9)

    def test_incompatible_dimensions_are_rejected(self) -> None:
        determination = evaluate_obligation(Obligation("O", population={"kind": "board"}, **BOARD), _world({"value": 5, "unit": "kg"}))
        self.assertEqual(determination.status, DeterminationStatus.INCOMPLETE)
        self.assertIn(DeterminationReason.INCOMPATIBLE_MEASUREMENT_DIMENSION.value, determination.reasons)

    def test_schema_drift_is_detected(self) -> None:
        from tests.conformance import schemas

        schemas.requires_schemas(self)
        validator = schemas.validator("determination.schema.json")
        determination = evaluate_obligation(load_obligation(EXAMPLE / "requirement.json"), load_world(EXAMPLE / "project-world.json"))
        self.assertTrue(validator.is_valid(determination.to_dict()))
        self.assertFalse(validator.is_valid({**determination.to_dict(), "driftedField": 1}))

    def test_a_proof_belongs_to_the_run_that_carries_it(self) -> None:
        from tests.conformance import schemas

        schemas.requires_schemas(self)
        obligation = load_obligation(EXAMPLE / "requirement.json")
        world = load_world(EXAMPLE / "project-world.json")
        determination = evaluate_obligation(obligation, world)
        proof = Proof.from_determination(determination).to_dict()
        with TemporaryDirectory() as directory:
            store = RunStore(directory)
            frozen = store.freeze(world, obligation)
            store.publish(create_run(world, frozen, determination, proof=proof))
            published = store.load_canonical()

        # The run schema embeds the proof schema, so an invalid proof cannot
        # ride inside a valid run.
        validator = schemas.validator("run.schema.json")
        self.assertTrue(validator.is_valid(published))
        self.assertFalse(validator.is_valid({**published, "proof": {"banana": "hello"}}))

        # And a schema-valid proof describing some other evaluation is refused
        # by the semantic layer, which JSON Schema cannot express.
        validate_semantics("run.schema.json", published)
        with self.assertRaises(ConformanceError):
            validate_semantics("run.schema.json", {**published, "proof": {**proof, "result": "MET"}})
        with self.assertRaises(ConformanceError):
            store.publish(create_run(world, frozen, determination, proof={**proof, "requirementId": "REQ-OTHER"}))

    def test_aec_vocabulary_is_injected_not_built_in(self) -> None:
        kernel = (ROOT / "packages/sfc-core/src/sfc/assurance.py").read_text(encoding="utf-8").lower()
        for term in ("electrical", "panel", "clearance", "inches"):
            self.assertNotIn(term, kernel)
        pack = Vocabulary.from_dict({
            "vocabularyId": "gate", "version": "1",
            "kinds": [{"canonical": "board", "aliases": ["electricdistributionboard"]}],
        })
        world = ProjectWorld("p", (WorldElement("B-1", "electricdistributionboard", {"working_clearance": {"value": 1.0668, "unit": "m"}}),))
        obligation = Obligation("O", population={"kind": "board"}, **BOARD)
        self.assertEqual(evaluate_obligation(obligation, world).status, DeterminationStatus.INCOMPLETE)
        self.assertEqual(evaluate_obligation(obligation, world, vocabulary=pack).status, DeterminationStatus.MET)

    def test_the_cli_behaves_as_an_installed_user_sees_it(self) -> None:
        from contextlib import redirect_stdout
        import io

        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "run.json"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main([
                    "verify", str(EXAMPLE / "requirement.json"), str(EXAMPLE / "project-world.json"),
                    "--store", str(root / "store"), "--output", str(output),
                ])
            self.assertEqual(code, 0)
            self.assertEqual(read_json(output)["determination"]["determination"], "NOT_MET")
            self.assertIn("Published", buffer.getvalue())

    def test_local_private_is_enforced_by_property_not_by_name(self) -> None:
        misnamed = GatewayRoute("route-local-private", "sfc/local-private", "vendor", "frontier")
        self.assertFalse(misnamed.is_local)
        with self.assertRaises(PermissionError):
            GatewayPolicy(local_only=True).authorize(misnamed)

        with TemporaryDirectory() as directory:
            previous = {key: os.environ.get(key) for key in ("SFC_GATEWAY_PROVIDER", "SFC_PROVIDER", "SFC_GATEWAY_LOCAL_ONLY")}
            os.environ.update({"SFC_GATEWAY_PROVIDER": "environment", "SFC_PROVIDER": "openai-compatible", "SFC_GATEWAY_LOCAL_ONLY": "true"})
            try:
                gateway = build_default_gateway(ledger_path=Path(directory) / "usage.jsonl")
                route = gateway.router.select("sfc/local-private")
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
        self.assertTrue(route.is_local)
        self.assertIs(route.execution_scope, ExecutionScope.LOCAL)
        self.assertIs(route.data_residency, DataResidency.DEVICE)
        self.assertFalse(route.network_required)

    def test_a_published_run_satisfies_every_invariant_and_its_schema(self) -> None:
        from tests.conformance import schemas

        schemas.requires_schemas(self)
        obligation = load_obligation(EXAMPLE / "requirement.json")
        world = load_world(EXAMPLE / "project-world.json")
        with TemporaryDirectory() as directory:
            store = RunStore(directory)
            frozen = store.freeze(world, obligation)
            determination = evaluate_obligation(obligation, world, vocabulary=Vocabulary.empty())
            validate_determination(determination)
            run = create_run(world, frozen, determination)
            path = store.publish(run)
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            schemas.assert_valid(self, "run.schema.json", on_disk)
            self.assertEqual(store.load_canonical()["runId"], run.run_id)
        self.assertEqual(on_disk["status"], "published")
        self.assertEqual(on_disk["determination"]["determination"], "NOT_MET")

    def test_publication_refuses_a_determination_that_breaks_an_invariant(self) -> None:
        obligation = load_obligation(EXAMPLE / "requirement.json")
        world = load_world(EXAMPLE / "project-world.json")
        with TemporaryDirectory() as directory:
            store = RunStore(directory)
            frozen = store.freeze(world, obligation)
            run = create_run(world, frozen, _met_on_nothing())
            with self.assertRaises(AssuranceError):
                store.publish(run)
            # The canonical pointer never moved.
            self.assertIsNone(store.load_canonical())


def _evaluated_all_of_nothing():
    """A determination stating a coverage fraction over an empty population."""
    from sfc.models import Determination

    return Determination(
        requirement_id="REQ-1",
        obligation_id="OBL-1",
        quantifier=Quantifier.ALL,
        expected_population=0,
        evaluated_population=0,
        conforming=0,
        coverage=1.0,
        status=DeterminationStatus.INCOMPLETE,
    )


def _met_on_nothing():
    """A determination claiming compliance over an empty population."""
    from sfc.models import Determination

    return Determination(
        requirement_id="REQ-1",
        obligation_id="OBL-1",
        quantifier=Quantifier.ALL,
        expected_population=0,
        evaluated_population=0,
        conforming=0,
        coverage=None,
        status=DeterminationStatus.MET,
    )


if __name__ == "__main__":
    unittest.main()
