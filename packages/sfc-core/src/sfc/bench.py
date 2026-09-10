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
        "metrics": {
            "accuracy": "not_scored_without_fixture_truth",
            "evidencePrecision": "not_scored_without_fixture_truth",
            "evidenceRecall": "not_scored_without_fixture_truth",
            "counterexamplePrecision": "not_scored_without_fixture_truth",
            "counterexampleRecall": "not_scored_without_fixture_truth",
            "falseClosureRate": "not_scored_without_fixture_truth",
            "populationCoverage": determination.coverage,
            "unsupportedClaims": "not_scored_without_agent_trace",
            "tokensPerDetermination": "not_scored_without_provider",
            "costPerDetermination": "not_scored_without_provider",
        },
    }
    truth_path = root_path / "truth.json"
    if truth_path.exists():
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        expected_status = truth.get("status")
        result["metrics"]["accuracy"] = 1.0 if expected_status == determination.status.value else 0.0
        result["metrics"]["falseClosureRate"] = 1.0 if determination.status.value == "MET" and expected_status != "MET" else 0.0
        expected_evidence = set(truth.get("expectedEvidenceIds", []))
        predicted_evidence = set(determination.evidence_ids)
        if expected_evidence or predicted_evidence:
            intersection = len(expected_evidence & predicted_evidence)
            result["metrics"]["evidencePrecision"] = intersection / len(predicted_evidence) if predicted_evidence else 0.0
            result["metrics"]["evidenceRecall"] = intersection / len(expected_evidence) if expected_evidence else 0.0
        expected_counterexamples = set(truth.get("expectedCounterexamples", []))
        predicted_counterexamples = {item.subject for item in determination.counterexamples}
        if expected_counterexamples or predicted_counterexamples:
            intersection = len(expected_counterexamples & predicted_counterexamples)
            result["metrics"]["counterexamplePrecision"] = intersection / len(predicted_counterexamples) if predicted_counterexamples else 0.0
            result["metrics"]["counterexampleRecall"] = intersection / len(expected_counterexamples) if expected_counterexamples else 0.0
        if "expectedCoverage" in truth:
            result["metrics"]["populationCoverage"] = 1.0 if determination.coverage == truth["expectedCoverage"] else 0.0
        result["truthStatus"] = expected_status
    return result
