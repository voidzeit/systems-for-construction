"""Safe, deliberately limited diagnostic bundle generation."""

from __future__ import annotations

from pathlib import Path
import json
import platform
import sys
import zipfile

from .models import _utc_now


def create_support_bundle(output: str | Path, root: str | Path = ".sfc") -> Path:
    output_path = Path(output)
    root_path = Path(root)
    canonical = root_path / "canonical-run.json"
    frozen = root_path / "frozen-inputs.json"
    usage = root_path / "usage.jsonl"

    manifest = {
        "format": "sfc-support-bundle-1",
        "createdAt": _utc_now(),
        "contents": ["manifest.json", "diagnostics.json", "runtime.json", "usage.json", "failures.json", "collection-report.json"],
        "redactions": ["prompts", "secrets", "model payloads", "PDFs", "RVT files", "private project data"],
    }
    diagnostics = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    runtime = {
        "hasCanonicalRun": canonical.exists(),
        "hasFrozenInputs": frozen.exists(),
    }
    usage_records = []
    if usage.exists():
        usage_records = [json.loads(line) for line in usage.read_text(encoding="utf-8").splitlines() if line.strip()]
    failures = []
    collection_report = {"collected": list(manifest["contents"]), "omitted": manifest["redactions"]}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in {
            "manifest.json": manifest,
            "diagnostics.json": diagnostics,
            "runtime.json": runtime,
            "usage.json": usage_records,
            "failures.json": failures,
            "collection-report.json": collection_report,
        }.items():
            bundle.writestr(name, json.dumps(content, ensure_ascii=False, indent=2) + "\n")
    return output_path

