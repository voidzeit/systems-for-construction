"""The CLI is the main public surface, so it is tested as a user meets it.

Every case asserts three things where they apply: the exit code a script would
branch on, the artifact left on disk, and the JSON printed to stdout.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import json
import os
import subprocess
import sys
import unittest

from sfc.cli import build_parser, main
from sfc.io import read_json

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples/electrical-panel-clearance"
IFC = ROOT / "examples/ifc-panel-clearance"


def run(*argv: str) -> tuple[int, str, str]:
    """Invoke the CLI in process and capture what a user would see."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ParserTests(unittest.TestCase):
    def test_every_subcommand_is_reachable(self) -> None:
        parser = build_parser()
        actions = [action for action in parser._actions if action.dest == "command"]
        self.assertEqual(len(actions), 1)
        expected = {
            "verify", "inspect", "doctor", "support-bundle", "ifc-import", "pdf-import",
            "admit-evidence", "investigate", "bench", "report", "readiness", "serve",
            "gateway", "vocabulary",
        }
        self.assertEqual(set(actions[0].choices), expected)

    def test_a_missing_command_is_a_usage_error(self) -> None:
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            main([])
        self.assertEqual(raised.exception.code, 2)

    def test_an_unknown_command_is_a_usage_error(self) -> None:
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            main(["not-a-command"])
        self.assertEqual(raised.exception.code, 2)

    def test_help_documents_the_exit_codes(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            main(["--help"])
        self.assertIn("exit codes", out.getvalue())


class VerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)

    def test_a_closed_determination_exits_zero_and_publishes(self) -> None:
        output = self.root / "run.json"
        code, stdout, _ = run(
            "verify", str(EXAMPLE / "requirement.json"), str(EXAMPLE / "project-world.json"),
            "--store", str(self.root / "store"), "--output", str(output),
        )
        self.assertEqual(code, 0)
        self.assertTrue(output.is_file())
        document = read_json(output)
        self.assertEqual(document["determination"]["determination"], "NOT_MET")
        self.assertEqual(document["status"], "published")
        self.assertIn(document["runId"], stdout)
        self.assertIn("Published", stdout)
        # The canonical pointer moved to the same run.
        canonical = read_json(self.root / "store" / "canonical-run.json")
        self.assertEqual(canonical["runId"], document["runId"])

    def test_stdout_is_parseable_json_followed_by_one_status_line(self) -> None:
        code, stdout, _ = run(
            "verify", str(EXAMPLE / "requirement.json"), str(EXAMPLE / "project-world.json"),
            "--store", str(self.root / "store"), "--output", str(self.root / "run.json"),
        )
        self.assertEqual(code, 0)
        body, _, trailer = stdout.rpartition("\n}\n")
        self.assertEqual(json.loads(body + "\n}")["status"], "published")
        self.assertTrue(trailer.startswith("Published "))

    def test_an_open_determination_exits_one(self) -> None:
        requirement = json.loads((EXAMPLE / "requirement.json").read_text(encoding="utf-8"))
        requirement["population"] = {"kind": "nothing_matches_this", "minimumExpected": 1}
        path = self.root / "requirement.json"
        path.write_text(json.dumps(requirement), encoding="utf-8")
        output = self.root / "run.json"
        code, _, _ = run(
            "verify", str(path), str(EXAMPLE / "project-world.json"),
            "--store", str(self.root / "store"), "--output", str(output),
        )
        self.assertEqual(code, 1)
        determination = read_json(output)["determination"]
        self.assertEqual(determination["determination"], "INCOMPLETE")
        self.assertIn("EMPTY_POPULATION_UNRESOLVED", determination["reasons"])
        self.assertIsNone(determination["coverage"])

    def test_no_vocabulary_changes_what_the_kernel_will_assert(self) -> None:
        requirement = json.loads((IFC / "requirement.json").read_text(encoding="utf-8"))
        requirement["population"] = {"kind": "electrical_panel", "minimumExpected": 1}
        path = self.root / "aliased.json"
        path.write_text(json.dumps(requirement), encoding="utf-8")
        world = self.root / "world.json"
        self.assertEqual(run("ifc-import", str(IFC / "demo.ifc"), "--output", str(world))[0], 0)

        output = self.root / "run.json"
        with_pack, _, _ = run("verify", str(path), str(world), "--store", str(self.root / "s1"), "--output", str(output))
        self.assertEqual(with_pack, 0)
        self.assertEqual(read_json(output)["determination"]["determination"], "NOT_MET")

        bare, _, _ = run("verify", str(path), str(world), "--store", str(self.root / "s2"), "--output", str(output), "--no-vocabulary")
        self.assertEqual(bare, 1)
        self.assertEqual(read_json(output)["determination"]["determination"], "INCOMPLETE")

    def test_an_unreadable_requirement_exits_two_without_a_traceback(self) -> None:
        code, stdout, stderr = run("verify", str(self.root / "missing.json"), str(EXAMPLE / "project-world.json"))
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("FileNotFoundError", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_malformed_json_exits_two(self) -> None:
        path = self.root / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        code, _, stderr = run("verify", str(path), str(EXAMPLE / "project-world.json"))
        self.assertEqual(code, 2)
        self.assertIn("JSONDecodeError", stderr)

    def test_an_obligation_with_a_wrong_dimension_exits_two(self) -> None:
        requirement = json.loads((EXAMPLE / "requirement.json").read_text(encoding="utf-8"))
        requirement["predicate"] = {"property": "working_clearance", "operator": ">=", "value": 36, "unit": "kg"}
        path = self.root / "wrong-unit.json"
        path.write_text(json.dumps(requirement), encoding="utf-8")
        code, _, stderr = run("verify", str(path), str(EXAMPLE / "project-world.json"), "--store", str(self.root / "store"))
        self.assertEqual(code, 2)
        self.assertIn("mass", stderr)


class ReadOnlyCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)

    def test_inspect_summarizes_the_snapshot(self) -> None:
        code, stdout, _ = run("inspect", str(EXAMPLE / "project-world.json"))
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["elements"], 18)
        self.assertEqual(payload["byKind"], {"electrical_panel": 18})
        self.assertEqual(len(payload["snapshotHash"]), 64)

    def test_doctor_reports_the_runtime(self) -> None:
        code, stdout, _ = run("doctor", "--store", str(self.root / "store"))
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["canonicalRun"])

    def test_vocabulary_prints_the_pack_a_run_would_use(self) -> None:
        code, stdout, _ = run("vocabulary")
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["vocabularyId"], "sfc.vocabulary.aec-core")

        code, stdout, _ = run("vocabulary", "--no-vocabulary")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["kinds"], [])

    def test_ifc_import_writes_a_project_world_with_units(self) -> None:
        output = self.root / "world.json"
        code, stdout, _ = run("ifc-import", str(IFC / "demo.ifc"), "--output", str(output))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["elements"], 2)
        document = read_json(output)
        self.assertEqual(document["metadata"]["units"]["length"], "m")
        self.assertEqual(document["elements"][0]["properties"]["WorkingClearance"]["unit"], "m")

    def test_support_bundle_is_written(self) -> None:
        store = self.root / "store"
        run("verify", str(EXAMPLE / "requirement.json"), str(EXAMPLE / "project-world.json"),
            "--store", str(store), "--output", str(self.root / "run.json"))
        bundle = self.root / "bundle.zip"
        code, stdout, _ = run("support-bundle", "--output", str(bundle), "--store", str(store))
        self.assertEqual(code, 0)
        self.assertTrue(bundle.is_file())
        self.assertIn("bundle.zip", stdout)


class EvidenceAndReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.run_path = self.root / "run.json"
        run("verify", str(EXAMPLE / "requirement.json"), str(EXAMPLE / "project-world.json"),
            "--store", str(self.root / "store"), "--output", str(self.run_path))

    def _ledger(self, authority: float) -> Path:
        path = self.root / "ledger.json"
        path.write_text(json.dumps([{
            "evidenceId": "E-1", "sourceId": "s", "sourceType": "model_element",
            "locator": {"elementId": "LP-01"}, "observedValue": {"value": 42, "unit": "in"},
            "authority": authority, "confidence": 1.0, "provenance": ["fixture"],
        }]), encoding="utf-8")
        return path

    def test_admitted_evidence_exits_zero(self) -> None:
        output = self.root / "admitted.json"
        code, stdout, _ = run("admit-evidence", str(self._ledger(0.9)), "--output", str(output))
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(len(payload["admitted"]), 1)
        self.assertEqual(payload["rejected"], [])
        self.assertTrue(read_json(output)["admitted"][0]["admitted"])

    def test_rejected_evidence_exits_one_and_says_why(self) -> None:
        output = self.root / "admitted.json"
        code, stdout, _ = run("admit-evidence", str(self._ledger(0.1)), "--output", str(output))
        self.assertEqual(code, 1)
        payload = json.loads(stdout)
        self.assertEqual(payload["admitted"], [])
        self.assertEqual(payload["rejected"][0]["evidenceId"], "E-1")
        self.assertTrue(payload["rejected"][0]["reason"])

    def test_reports_render_in_every_format(self) -> None:
        for fmt, marker in (("json", '"runId"'), ("csv", "run_id,"), ("html", "<!doctype html>")):
            with self.subTest(format=fmt):
                output = self.root / f"report.{fmt}"
                code, stdout, _ = run("report", str(self.run_path), "--format", fmt, "--output", str(output))
                self.assertEqual(code, 0)
                self.assertIn(str(output), stdout)
                self.assertIn(marker, output.read_text(encoding="utf-8"))

    def test_an_unsupported_report_format_is_a_usage_error(self) -> None:
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            main(["report", str(self.run_path), "--format", "pdf", "--output", str(self.root / "x")])
        self.assertEqual(raised.exception.code, 2)

    def test_the_html_report_shows_the_unit_and_not_a_raw_mapping(self) -> None:
        output = self.root / "report.html"
        run("report", str(self.run_path), "--format", "html", "--output", str(output))
        body = output.read_text(encoding="utf-8")
        self.assertIn("29.4 in", body)
        self.assertNotIn("&#x27;value&#x27;", body)

    def test_readiness_reads_a_published_run(self) -> None:
        output = self.root / "readiness.json"
        code, stdout, _ = run("readiness", str(self.run_path), "--output", str(output))
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertIsNotNone(payload["score"])
        self.assertEqual(payload["basis"]["requirements"], 1)
        self.assertEqual(read_json(output)["score"], payload["score"])


class InvestigateAndBenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)

    def test_investigate_publishes_a_run_from_an_ifc_file(self) -> None:
        output = self.root / "investigation.json"
        code, stdout, _ = run(
            "investigate", str(IFC / "demo.ifc"),
            "--statement", "Every electrical distribution board must maintain 36 inches of working clearance",
            "--store", str(self.root / "store"), "--output", str(output),
        )
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["run"]["determination"]["determination"], "NOT_MET")
        self.assertEqual(payload["agent"]["actions"], 3)
        # The agent proposed; it did not publish.
        self.assertEqual(payload["run"]["status"], "published")
        self.assertEqual(payload["admittedEvidence"][0]["measurement"]["normalizedUnit"], "in")
        self.assertTrue(output.is_file())

    def test_an_unsupported_statement_exits_two(self) -> None:
        code, _, stderr = run(
            "investigate", str(IFC / "demo.ifc"),
            "--statement", "Panels should generally be accessible",
            "--store", str(self.root / "store"), "--output", str(self.root / "out.json"),
        )
        self.assertEqual(code, 2)
        self.assertIn("unsupported requirement", stderr)

    def test_bench_scores_against_the_fixture_truth(self) -> None:
        output = self.root / "bench.json"
        code, stdout, _ = run("bench", str(EXAMPLE), "--output", str(output))
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["metrics"]["accuracy"], 1.0)
        self.assertEqual(payload["metrics"]["falseClosureRate"], 0.0)
        self.assertEqual(read_json(output)["status"], "NOT_MET")


SOURCE = ROOT / "packages/sfc-core/src"


def _subprocess_environment() -> dict[str, str]:
    """Give a child process the same import path pytest gives this one.

    Without it these cases would only pass after ``pip install -e .``, and the
    suite is meant to run from a clean clone too.
    """
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = f"{SOURCE}{os.pathsep}{existing}" if existing else str(SOURCE)
    return environment


class InstalledEntryPointTests(unittest.TestCase):
    """The console scripts declared in pyproject must actually run."""

    def _script(self, name: str) -> Path | None:
        directory = Path(sys.executable).parent
        for candidate in (directory / name, directory / f"{name}.exe", directory / "Scripts" / name, directory / "Scripts" / f"{name}.exe"):
            if candidate.is_file():
                return candidate
        return None

    def test_the_sfc_console_script_runs(self) -> None:
        script = self._script("sfc")
        if script is None:
            self.skipTest("sfc console script is not installed in this environment")
        result = subprocess.run([str(script), "doctor"], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "ok")

    def test_the_module_entry_point_runs(self) -> None:
        result = subprocess.run([sys.executable, "-m", "sfc", "doctor"], capture_output=True, text=True, cwd=str(ROOT), env=_subprocess_environment())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "ok")

    def test_the_module_entry_point_propagates_the_exit_code(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "sfc", "verify", "no-such-file.json", "no-such-world.json"],
            capture_output=True, text=True, cwd=str(ROOT), env=_subprocess_environment(),
        )
        self.assertEqual(result.returncode, 2)

    def test_the_mcp_console_script_is_declared(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('sfc = "sfc.cli:main"', pyproject)
        self.assertIn('sfc-mcp = "sfc.mcp:main"', pyproject)


class StudioResolutionTests(unittest.TestCase):
    def test_the_studio_resolves_independently_of_the_working_directory(self) -> None:
        from sfc.server import studio_path

        with TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                self.assertIsNotNone(studio_path(), "the Studio must not depend on the working directory")
            finally:
                os.chdir(previous)

    def test_an_explicit_path_wins(self) -> None:
        from sfc.server import studio_path

        with TemporaryDirectory() as directory:
            explicit = Path(directory) / "custom.html"
            explicit.write_text("<h1>custom</h1>", encoding="utf-8")
            self.assertEqual(studio_path(explicit), explicit)

    def test_an_install_without_a_studio_resolves_to_none(self) -> None:
        from unittest import mock
        from sfc import server

        with TemporaryDirectory() as directory, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(server.STUDIO_VARIABLE, None)
            absent = Path(directory) / "absent" / "index.html"
            with mock.patch.object(server, "_REPOSITORY_STUDIO", absent):
                self.assertIsNone(server.studio_path())
                self.assertIsNone(server.studio_path(Path(directory) / "also-absent.html"))

    def test_the_environment_variable_is_honoured(self) -> None:
        from unittest import mock
        from sfc import server

        with TemporaryDirectory() as directory:
            configured = Path(directory) / "from-env.html"
            configured.write_text("<h1>env</h1>", encoding="utf-8")
            with mock.patch.dict(os.environ, {server.STUDIO_VARIABLE: str(configured)}):
                self.assertEqual(server.studio_path(), configured)


if __name__ == "__main__":
    unittest.main()
