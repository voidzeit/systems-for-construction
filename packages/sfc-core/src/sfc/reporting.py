"""Portable JSON, CSV and HTML reports from canonical SFC runs."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any
import csv
import io
import json


def determination_csv(run: dict[str, Any]) -> str:
    determination = run["determination"]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["run_id", "requirement_id", "status", "expected", "evaluated", "conforming", "coverage", "counterexamples"])
    writer.writerow([
        run.get("runId"), determination.get("requirementId"), determination.get("determination"),
        determination["population"].get("expected"), determination["population"].get("evaluated"),
        determination.get("conforming"), determination.get("coverage"), len(determination.get("counterexamples", [])),
    ])
    return output.getvalue()


def determination_html(run: dict[str, Any]) -> str:
    determination = run["determination"]
    status = escape(str(determination.get("determination", "UNKNOWN")))
    counterexamples = determination.get("counterexamples", [])
    rows = "".join(
        f"<tr><td>{escape(str(item.get('subject', '')))}</td><td>{escape(str(item.get('observed', '')))}</td><td>{escape(str(item.get('expected', '')))}</td></tr>"
        for item in counterexamples
    ) or "<tr><td colspan='3'>None</td></tr>"
    return f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><title>SFC Determination</title>
<style>body{{font-family:system-ui;max-width:900px;margin:3rem auto;padding:0 1rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:.5rem;text-align:left}}.status{{font-weight:700}}</style></head>
<body><h1>SFC Determination</h1><p class='status'>{status}</p>
<p>Run <code>{escape(str(run.get('runId')))}</code>; coverage {determination.get('coverage')}; {determination.get('conforming')} of {determination['population'].get('expected')} conforming.</p>
<h2>Counterexamples</h2><table><thead><tr><th>Subject</th><th>Observed</th><th>Expected</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""


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

