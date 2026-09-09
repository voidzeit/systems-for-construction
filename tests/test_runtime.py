import json
from pathlib import Path
import tempfile
import unittest

from sfc.assurance import evaluate_obligation
from sfc.io import load_obligation, load_world
from sfc.runtime import RunStore, create_run


ROOT = Path(__file__).parents[1]


class RuntimeTests(unittest.TestCase):
    def test_freeze_and_publish_are_reproducible(self) -> None:
        obligation = load_obligation(ROOT / "examples/electrical-panel-clearance/requirement.json")
        world = load_world(ROOT / "examples/electrical-panel-clearance/project-world.json")
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(directory)
            frozen = store.freeze(world, obligation)
            run = create_run(world, frozen, evaluate_obligation(obligation, world))
            path = store.publish(run)
            self.assertTrue(path.exists())
            canonical = store.load_canonical()
            self.assertEqual(canonical["runId"], run.run_id)
            self.assertEqual(canonical["inputHash"], run.input_hash)
            self.assertEqual(canonical["determination"]["population"]["expected"], 18)

