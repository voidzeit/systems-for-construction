"""The first public SFC command line workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys

from .assurance import evaluate_obligation
from .io import load_obligation, load_world, read_json, write_json
from .models import DeterminationStatus
from .runtime import RunStore, create_run
from .support import create_support_bundle
from .bench import run_benchmark
from .ifc import load_ifc
from .reporting import write_report
from .server import serve
from .authority import EvidenceAuthority, EvidenceAdmissionError
from .models import Evidence
from .pdf import load_pdf
from .investigation import investigate_and_publish
from .http_providers import provider_from_environment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sfc", description="Systems for Construction CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="evaluate an obligation against a Project World")
    verify.add_argument("requirement", type=Path)
    verify.add_argument("project_world", type=Path)
    verify.add_argument("--output", type=Path, default=Path(".sfc/last-run.json"))
    verify.add_argument("--store", type=Path, default=Path(".sfc"))

    inspect = sub.add_parser("inspect", help="inspect a Project World")
    inspect.add_argument("project_world", type=Path)

    doctor = sub.add_parser("doctor", help="check the local SFC runtime")
    doctor.add_argument("--store", type=Path, default=Path(".sfc"))

    bundle = sub.add_parser("support-bundle", help="create a redacted diagnostic bundle")
    bundle.add_argument("--output", type=Path, default=Path("support-bundle.zip"))
    bundle.add_argument("--store", type=Path, default=Path(".sfc"))

    ifc_import = sub.add_parser("ifc-import", help="translate an IFC STEP file into a Project World JSON snapshot")
    ifc_import.add_argument("ifc_file", type=Path)
    ifc_import.add_argument("--output", type=Path, required=True)

    pdf_import = sub.add_parser("pdf-import", help="translate PDF pages into a Project World JSON snapshot")
    pdf_import.add_argument("pdf_file", type=Path)
    pdf_import.add_argument("--output", type=Path, required=True)

    admit = sub.add_parser("admit-evidence", help="apply deterministic evidence authority to a JSON ledger")
    admit.add_argument("ledger", type=Path)
    admit.add_argument("--output", type=Path, required=True)
    admit.add_argument("--min-authority", type=float, default=0.6)

    investigate = sub.add_parser("investigate", help="compile a natural-language requirement and run a bounded reference investigation")
    investigate.add_argument("source", type=Path, help="Project World JSON or IFC STEP file")
    investigate.add_argument("--statement", required=True)
    investigate.add_argument("--output", type=Path, default=Path(".sfc/investigation.json"))
    investigate.add_argument("--store", type=Path, default=Path(".sfc"))
    investigate.add_argument("--provider", choices=["reference", "environment"], default="reference", help="provider mode; environment reads SFC_PROVIDER and its credentials")

    bench = sub.add_parser("bench", help="run a deterministic synthetic benchmark fixture")
    bench.add_argument("fixture", type=Path)
    bench.add_argument("--output", type=Path)

    report = sub.add_parser("report", help="render a run as JSON, CSV or HTML")
    report.add_argument("run", type=Path)
    report.add_argument("--format", choices=["json", "csv", "html"], required=True)
    report.add_argument("--output", type=Path, required=True)

    server = sub.add_parser("serve", help="serve a local read-only HTTP view")
    server.add_argument("--world", type=Path)
    server.add_argument("--run", type=Path)
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8787)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify":
        return _verify(args)
    if args.command == "inspect":
        return _inspect(args)
    if args.command == "doctor":
        return _doctor(args)
    if args.command == "support-bundle":
        return _support_bundle(args)
    if args.command == "ifc-import":
        return _ifc_import(args)
    if args.command == "pdf-import":
        return _pdf_import(args)
    if args.command == "admit-evidence":
        return _admit_evidence(args)
    if args.command == "investigate":
        return _investigate(args)
    if args.command == "bench":
        return _bench(args)
    if args.command == "report":
        return _report(args)
    if args.command == "serve":
        serve(args.world, args.run, args.host, args.port)
        return 0
    return 2


def _verify(args: argparse.Namespace) -> int:
    obligation = load_obligation(args.requirement)
    world = load_world(args.project_world)
    store = RunStore(args.store)
    frozen = store.freeze(world, obligation)
    determination = evaluate_obligation(obligation, world)
    run = create_run(world, frozen, determination)
    path = store.publish(run)
    output = run.to_dict()
    write_json(args.output, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Published {run.run_id} to {path}")
    return 0 if determination.status in {DeterminationStatus.MET, DeterminationStatus.NOT_MET} else 1


def _inspect(args: argparse.Namespace) -> int:
    world = load_world(args.project_world)
    by_kind: dict[str, int] = {}
    for element in world.elements:
        by_kind[element.kind] = by_kind.get(element.kind, 0) + 1
    print(json.dumps({"projectId": world.project_id, "elements": len(world.elements), "byKind": by_kind, "snapshotHash": world.snapshot_hash()}, indent=2))
    return 0


def _doctor(args: argparse.Namespace) -> int:
    store = RunStore(args.store)
    print(json.dumps({"status": "ok", "python": sys.version.split()[0], "platform": platform.platform(), "store": str(store.root), "canonicalRun": store.load_canonical() is not None}, indent=2))
    return 0


def _support_bundle(args: argparse.Namespace) -> int:
    path = create_support_bundle(args.output, args.store)
    print(path)
    return 0


def _ifc_import(args: argparse.Namespace) -> int:
    world = load_ifc(args.ifc_file)
    write_json(args.output, world.to_dict())
    print(json.dumps({"projectId": world.project_id, "elements": len(world.elements), "output": str(args.output)}, indent=2))
    return 0


def _pdf_import(args: argparse.Namespace) -> int:
    world = load_pdf(args.pdf_file)
    write_json(args.output, world.to_dict())
    print(json.dumps({"projectId": world.project_id, "pages": len(world.elements), "output": str(args.output)}, indent=2))
    return 0


def _admit_evidence(args: argparse.Namespace) -> int:
    source = read_json(args.ledger)
    records = source if isinstance(source, list) else source.get("evidence", [source])
    authority = EvidenceAuthority(args.min_authority)
    admitted = []
    rejected = []
    for raw in records:
        try:
            admitted.append(authority.admit(Evidence.from_dict(raw)).to_dict())
        except (EvidenceAdmissionError, ValueError) as error:
            rejected.append({"evidenceId": raw.get("evidenceId"), "reason": str(error)})
    result = {"admitted": admitted, "rejected": rejected, "policy": {"minimumAuthority": args.min_authority}}
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not rejected else 1


def _investigate(args: argparse.Namespace) -> int:
    world = load_ifc(args.source) if args.source.suffix.lower() == ".ifc" else load_world(args.source)
    provider = provider_from_environment() if args.provider == "environment" else None
    publication = investigate_and_publish(world, args.statement, store=RunStore(args.store), provider=provider)
    result = {
        "agent": {"agentId": publication.agent.agent_id, "actions": publication.agent.actions, "terminalReason": publication.agent.terminal_reason, "findings": [{"statement": finding.statement, "evidenceIds": list(finding.evidence_ids)} for finding in publication.agent.findings]},
        "admittedEvidence": [item.to_dict() for item in publication.admitted_evidence],
        "proof": publication.proof.to_dict(),
        "run": publication.run.to_dict(),
    }
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if publication.determination.status in {DeterminationStatus.MET, DeterminationStatus.NOT_MET} else 1


def _bench(args: argparse.Namespace) -> int:
    result = run_benchmark(args.fixture)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["metrics"].get("accuracy", 1.0) in {1.0, "not_scored_without_fixture_truth"} else 1


def _report(args: argparse.Namespace) -> int:
    destination = write_report(args.run, args.output, args.format)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
