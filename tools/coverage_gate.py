"""Assert measured coverage against a floor, globally and per kernel module.

Coverage is a regression net, not a definition of quality. A suite can walk the
same 40% of the code a thousand times, so a single global percentage says
little about whether the engineering semantics are exercised. What it does do
well is notice when a change stops exercising something that used to be.

So the gate has two parts, and the second is the one that matters:

    GLOBAL     a floor over the whole runtime, including the surfaces whose
               coverage is not evidence of correctness - the HTTP server, the
               MCP adapter, the PDF reader
    KERNEL     a higher floor on the modules that decide what SFC asserts.
               A determination, a proof, a quantity, a document contract or a
               replay is where an uncovered branch is a semantic risk

Branch coverage, not line coverage: the whole subject is which way a decision
went, so a floor over lines alone would miss exactly what is worth measuring.

Usage:

    python -m coverage run --branch -m unittest discover -s tests -t .
    python -m coverage json -o coverage.json
    python tools/coverage_gate.py coverage.json
"""

from __future__ import annotations

from pathlib import Path
import json
import sys

#: A floor over everything, set below what is currently measured so ordinary
#: work does not trip it. Raise it when the measurement rises; never lower it
#: to make a change pass.
GLOBAL_FLOOR = 82.0

#: The modules that decide what SFC asserts about a project. An uncovered
#: branch here is an unexercised rule, so these are held higher.
KERNEL_FLOOR = 85.0

KERNEL_MODULES = (
    "assurance.py",      # quantifier semantics and the closing rules
    "conformance.py",    # the document invariants at the publication boundary
    "authority.py",      # what makes candidate evidence official
    "control_plane.py",  # governed transitions, and replay of them
    "work.py",           # Work Unit contract and lifecycle semantics
    "plugins.py",        # portable plugin/capability manifest semantics
    "evidence_room.py",  # evidence and document lifecycle, and replay of it
    "events.py",         # the event registry that makes replay fail closed
    "models.py",         # the contracts themselves
    "proofs.py",         # what a determination is turned into for audit
    "quantities.py",     # units, conversion and refusal to compare
    "requirements.py",   # requirement text to an evaluable obligation
    "runtime.py",        # freeze, validate, publish
    "vocabulary.py",     # the injected domain terms
)


def percentage(summary: dict) -> float:
    return float(summary.get("percent_covered", 0.0))


def evaluate(report: dict) -> tuple[list[str], list[str]]:
    """Return (failures, lines) for the report, without printing."""
    failures: list[str] = []
    lines: list[str] = []

    total = percentage(report["totals"])
    verdict = "PASS" if total >= GLOBAL_FLOOR else "FAIL"
    lines.append(f"  {verdict}  global {total:.1f}% (floor {GLOBAL_FLOOR:.0f}%)")
    if total < GLOBAL_FLOOR:
        failures.append(f"global coverage {total:.1f}% is below the {GLOBAL_FLOOR:.0f}% floor")

    measured = {Path(name).name: summary for name, summary in report["files"].items()}
    for module in KERNEL_MODULES:
        summary = measured.get(module)
        if summary is None:
            failures.append(f"kernel module {module} was not measured at all")
            lines.append(f"  FAIL  {module} not measured")
            continue
        covered = percentage(summary["summary"])
        verdict = "PASS" if covered >= KERNEL_FLOOR else "FAIL"
        lines.append(f"  {verdict}  {module} {covered:.1f}% (floor {KERNEL_FLOOR:.0f}%)")
        if covered < KERNEL_FLOOR:
            failures.append(f"{module} at {covered:.1f}% is below the {KERNEL_FLOOR:.0f}% kernel floor")
    return failures, lines


def main(argv: list[str]) -> int:
    source = Path(argv[1] if len(argv) > 1 else "coverage.json")
    if not source.exists():
        print(f"coverage report not found: {source}", file=sys.stderr)
        print("run: python -m coverage json -o coverage.json", file=sys.stderr)
        return 2
    report = json.loads(source.read_text(encoding="utf-8"))
    if not report["totals"].get("num_branches"):
        print("the report has no branch data; run coverage with --branch", file=sys.stderr)
        return 2

    failures, lines = evaluate(report)
    print("SFC COVERAGE GATE")
    for line in lines:
        print(line)
    if failures:
        print("\nfailed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("\nall floors held")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
