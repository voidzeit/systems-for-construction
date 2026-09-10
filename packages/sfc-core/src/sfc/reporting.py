"""Portable JSON, CSV and HTML reports from canonical SFC runs."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any
import csv
import io
import json


def format_measurement(value: Any) -> str:
    """Render an observed or expected value, keeping its unit visible."""
    if isinstance(value, dict) and isinstance(value.get("value"), (int, float)) and not isinstance(value.get("value"), bool):
        unit = value.get("unit")
        return f"{value['value']:g} {unit}" if unit else f"{value['value']:g}"
    return "" if value is None else str(value)


def format_coverage(value: Any) -> str:
    """Absent coverage stays absent. It is not rendered as zero or as one."""
    return "not applicable" if value is None else f"{value}"


def determination_csv(run: dict[str, Any]) -> str:
    determination = run["determination"]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["run_id", "requirement_id", "status", "expected", "evaluated", "conforming", "coverage", "counterexamples"])
    writer.writerow([
        run.get("runId"), determination.get("requirementId"), determination.get("determination"),
        determination["population"].get("expected"), determination["population"].get("evaluated"),
        determination.get("conforming"), format_coverage(determination.get("coverage")), len(determination.get("counterexamples", [])),
    ])
    return output.getvalue()


def determination_html(run: dict[str, Any]) -> str:
    determination = run["determination"]
    status = escape(str(determination.get("determination", "UNKNOWN")))
    counterexamples = determination.get("counterexamples", [])
    rows = "".join(
        f"<tr><td>{escape(str(item.get('subject', '')))}</td><td>{escape(format_measurement(item.get('observed')))}</td><td>{escape(format_measurement(item.get('expected')))}</td><td>{escape(_conversion(item))}</td></tr>"
        for item in counterexamples
    ) or "<tr><td colspan='4'>None</td></tr>"
    return f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><title>SFC Determination</title>
<style>body{{font-family:system-ui;max-width:900px;margin:3rem auto;padding:0 1rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:.5rem;text-align:left}}.status{{font-weight:700}}</style></head>
<body><h1>SFC Determination</h1><p class='status'>{status}</p>
<p>Run <code>{escape(str(run.get('runId')))}</code>; coverage {escape(format_coverage(determination.get('coverage')))}; {determination.get('conforming')} of {determination['population'].get('expected')} conforming.</p>
{_reasons_html(determination)}
<h2>Counterexamples</h2><table><thead><tr><th>Subject</th><th>Observed</th><th>Expected</th><th>Normalization</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""


def _conversion(counterexample: dict[str, Any]) -> str:
    measurement = counterexample.get("measurement") or {}
    raw_unit, normalized_unit = measurement.get("rawUnit"), measurement.get("normalizedUnit")
    if not raw_unit or not normalized_unit or raw_unit == normalized_unit:
        return ""
    return f"{measurement.get('rawValue'):g} {raw_unit} -> {measurement.get('normalizedValue'):g} {normalized_unit}"


def _reasons_html(determination: dict[str, Any]) -> str:
    reasons = determination.get("reasons") or []
    if not reasons:
        return ""
    items = "".join(f"<li><code>{escape(str(reason))}</code></li>" for reason in reasons)
    return f"<h2>Reasons</h2><ul>{items}</ul>"


def write_report(run_path: str | Path, output: str | Path, format: str) -> Path:
    run = json.loads(Path(run_path).read_text(encoding="utf-8"))
    destination = Path(output)
    if format == "json":
        destination.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif format == "csv":
        destination.write_text(determination_csv(run), encoding="utf-8")
    elif format == "html":
        destination.write_text(determination_html(run), encoding="utf-8")
    else:
        raise ValueError(f"unsupported report format: {format}")
    return destination

