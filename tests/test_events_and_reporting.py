import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sfc.events import Event, EventLog
from sfc.io import load_obligation, load_world
from sfc.assurance import evaluate_obligation
from sfc.reporting import determination_csv, determination_html
from sfc.runtime import RunStore, create_run
from sfc.bench import run_benchmark


ROOT = Path(__file__).parents[1]


class EventsAndReportingTests(unittest.TestCase):
    def test_event_log_is_append_only_and_filterable(self) -> None:
        with TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "events.jsonl")
            log.append(Event("obligation.accepted", "obl-1", {"status": "accepted"}, actor_id="human"))
            log.append(Event("obligation.verified", "obl-1", {"status": "verified"}, actor_id="agent"))
            self.assertEqual(len(log.read("obl-1")), 2)
            self.assertEqual(log.read("other"), [])

    def test_report_formats_contain_determination(self) -> None:
        obligation = load_obligation(ROOT / "examples/electrical-panel-clearance/requirement.json")
        world = load_world(ROOT / "examples/electrical-panel-clearance/project-world.json")
        with TemporaryDirectory() as directory:
            store = RunStore(directory)
            frozen = store.freeze(world, obligation)
            run = create_run(world, frozen, evaluate_obligation(obligation, world)).to_dict()
            self.assertIn("NOT_MET", determination_csv(run))
            self.assertIn("LP-18", determination_html(run))

    def test_benchmark_scores_evidence_and_counterexamples_when_truth_exists(self) -> None:
        result = run_benchmark(ROOT / "examples/electrical-panel-clearance")
        self.assertEqual(result["metrics"]["accuracy"], 1.0)
        self.assertEqual(result["metrics"]["evidencePrecision"], 1.0)
        self.assertEqual(result["metrics"]["evidenceRecall"], 1.0)
        self.assertEqual(result["metrics"]["counterexampleRecall"], 1.0)
