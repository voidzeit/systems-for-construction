from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.ifc import load_ifc
from sfc.investigation import investigate_and_publish
from sfc.runtime import RunStore


ROOT = Path(__file__).parents[1]


class InvestigationTests(unittest.TestCase):
    def test_end_to_end_requirement_to_canonical_run(self) -> None:
        world = load_ifc(ROOT / "examples/ifc-panel-clearance/demo.ifc")
        with TemporaryDirectory() as directory:
            publication = investigate_and_publish(
                world,
                "Every electrical distribution board must maintain 36 inches of working clearance",
                store=RunStore(directory),
            )
            self.assertEqual(publication.agent.actions, 3)
            self.assertEqual(publication.determination.status.value, "NOT_MET")
            # A witness satisfies the predicate; a counterexample refutes it.
            # These are different subjects, and the proof must not conflate them.
            self.assertEqual(publication.proof.witnesses, ("PANEL-IFC-01",))
            self.assertEqual(
                tuple(item["subject"] for item in publication.proof.counterexamples),
                ("PANEL-IFC-02",),
            )
            self.assertEqual(len(publication.run.evidence_ids), 2)
            self.assertEqual(publication.run.proof["result"], "NOT_MET")

