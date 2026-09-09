"""Reproducible benchmark runner for synthetic SFC fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .assurance import evaluate_obligation
from .io import load_obligation, load_world


def run_benchmark(root: str | Path) -> dict[str, Any]:
    root_path = Path(root)
    obligation = load_obligation(root_path / "requirement.json")
    world = load_world(root_path / "project-world.json")
    determination = evaluate_obligation(obligation, world)
    result: dict[str, Any] = {
        "fixture": root_path.name,
        "status": determination.status.value,
        "expected": determination.expected_population,
        "evaluated": determination.evaluated_population,
        "coverage": determination.coverage,
        "counterexamples": len(determination.counterexamples),
        "metrics": {"accuracy": "not_scored_without_fixture_truth", "evidencePrecision": "not_scored_without_fixture_truth", "evidenceRecall": "not_scored_without_fixture_truth"},
    }
    truth_path = root_path / "truth.json"
    if truth_path.exists():
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        expected_status = truth.get("status")
        result["metrics"]["accuracy"] = 1.0 if expected_status == determination.status.value else 0.0
        result["truthStatus"] = expected_status
    return result

