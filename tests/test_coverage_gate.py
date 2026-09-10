"""The coverage gate is itself tested, because a gate nobody checks is decor.

These tests assert the gate's decisions against synthetic reports rather than
measuring the real suite. Running coverage inside a coverage run would measure
the measurement, and the point here is only that the thresholds are applied and
that a missing kernel module is a failure rather than a silent pass.
"""

from __future__ import annotations

from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).parents[1]


def _gate():
    specification = importlib.util.spec_from_file_location("coverage_gate", ROOT / "tools/coverage_gate.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


GATE = _gate()


def _report(*, total: float, modules: dict[str, float] | None = None) -> dict:
    covered = dict.fromkeys(GATE.KERNEL_MODULES, 100.0)
    covered.update(modules or {})
    return {
        "totals": {"percent_covered": total, "num_branches": 100},
        "files": {
            f"packages/sfc-core/src/sfc/{name}": {"summary": {"percent_covered": value}}
            for name, value in covered.items()
        },
    }


class GateTests(unittest.TestCase):
    def test_a_report_above_every_floor_passes(self) -> None:
        failures, _ = GATE.evaluate(_report(total=GATE.GLOBAL_FLOOR + 1))
        self.assertEqual(failures, [])

    def test_a_global_percentage_below_the_floor_fails(self) -> None:
        failures, _ = GATE.evaluate(_report(total=GATE.GLOBAL_FLOOR - 0.1))
        self.assertEqual(len(failures), 1)
        self.assertIn("global coverage", failures[0])

    def test_a_kernel_module_below_the_higher_floor_fails(self) -> None:
        failures, _ = GATE.evaluate(_report(
            total=GATE.GLOBAL_FLOOR + 1,
            modules={"assurance.py": GATE.KERNEL_FLOOR - 0.1},
        ))
        self.assertEqual(len(failures), 1)
        self.assertIn("assurance.py", failures[0])

    def test_the_kernel_floor_is_higher_than_the_global_one(self) -> None:
        # Otherwise the second part of the gate would assert nothing.
        self.assertGreater(GATE.KERNEL_FLOOR, GATE.GLOBAL_FLOOR)

    def test_an_unmeasured_kernel_module_fails_rather_than_passing_quietly(self) -> None:
        report = _report(total=GATE.GLOBAL_FLOOR + 1)
        del report["files"]["packages/sfc-core/src/sfc/assurance.py"]
        failures, _ = GATE.evaluate(report)
        self.assertEqual(len(failures), 1)
        self.assertIn("was not measured", failures[0])

    def test_every_named_kernel_module_exists(self) -> None:
        for module in GATE.KERNEL_MODULES:
            with self.subTest(module=module):
                self.assertTrue((ROOT / "packages/sfc-core/src/sfc" / module).exists())

    def test_a_report_without_branch_data_is_rejected(self) -> None:
        import json
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.json"
            report = _report(total=99.0)
            report["totals"]["num_branches"] = 0
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(GATE.main(["coverage_gate.py", str(path)]), 2)

    def test_a_missing_report_is_an_error_not_a_pass(self) -> None:
        self.assertEqual(GATE.main(["coverage_gate.py", str(ROOT / "no-such-coverage.json")]), 2)


if __name__ == "__main__":
    unittest.main()
