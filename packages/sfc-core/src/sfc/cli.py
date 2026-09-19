"""The first public SFC command line workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys

from . import __version__
from .assurance import evaluate_obligation
from .io import load_obligation, load_world, read_json, write_json
from .models import CLOSING_STATUSES, Determination, Evidence
from .runtime import RunStore, create_run
from .support import create_support_bundle
from .bench import run_benchmark
from .ifc import load_ifc
from .reporting import write_report
from .server import serve
from .authority import EvidenceAuthority, EvidenceAdmissionError
from .pdf import load_pdf
from .investigation import investigate_and_publish
from .http_providers import provider_from_environment
from .gateway import serve_gateway
from .readiness import compute_readiness
from .vocabulary import Vocabulary, default_vocabulary
from .work import WorkUnit
from .plugins import PluginManifest, discover_plugin_manifests


def _add_vocabulary_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--vocabulary",
        type=Path,
        help="vocabulary pack file or directory; defaults to the bundled AEC pack, "
             "or SFC_VOCABULARY_PATH when set. Pass --no-vocabulary for the bare kernel.",
    )
    parser.add_argument(
        "--no-vocabulary",
        action="store_true",
        help="evaluate with no domain vocabulary, matching terms by spelling only",
    )


def _vocabulary(args: argparse.Namespace) -> Vocabulary:
    if getattr(args, "no_vocabulary", False):
        return Vocabulary.empty()
    if getattr(args, "vocabulary", None):
        return Vocabulary.load(args.vocabulary)
    return default_vocabulary()


EXIT_CODES = """exit codes:
  0  the command succeeded; for a determination, the requirement closed
     (MET, NOT_MET or NOT_APPLICABLE)
  1  the command ran but the requirement did not close (INCOMPLETE, UNKNOWN,
     STALE), or evidence was rejected
  2  usage error, unreadable input, or an obligation that cannot be evaluated
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sfc",
        description="Systems for Construction CLI",
        epilog=EXIT_CODES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="evaluate an obligation against a Project World")
    verify.add_argument("requirement", type=Path)
    verify.add_argument("project_world", type=Path)
    verify.add_argument("--output", type=Path, default=Path(".sfc/last-run.json"))
    verify.add_argument("--store", type=Path, default=Path(".sfc"))
    _add_vocabulary_option(verify)

    inspect = sub.add_parser("inspect", help="inspect a Project World")
    inspect.add_argument("project_world", type=Path)

    doctor = sub.add_parser("doctor", help="check the local SFC runtime")
    doctor.add_argument("--store", type=Path, default=Path(".sfc"))
    _add_vocabulary_option(doctor)

    parser.add_argument("--version", action="version", version=f"sfc {__version__}")

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
    _add_vocabulary_option(investigate)

    bench = sub.add_parser("bench", help="run a deterministic synthetic benchmark fixture")
    bench.add_argument("fixture", type=Path)
    bench.add_argument("--output", type=Path)
    _add_vocabulary_option(bench)

    vocabulary = sub.add_parser("vocabulary", help="show the vocabulary a determination would use")
    _add_vocabulary_option(vocabulary)

    report = sub.add_parser("report", help="render a run as JSON, CSV or HTML")
    report.add_argument("run", type=Path)
    report.add_argument("--format", choices=["json", "csv", "html"], required=True)
    report.add_argument("--output", type=Path, required=True)

    readiness = sub.add_parser("readiness", help="calculate the Project Readiness Index from published runs")
    readiness.add_argument("runs", nargs="+", type=Path)
    readiness.add_argument("--evidence", type=Path)
    readiness.add_argument("--output", type=Path)

    server = sub.add_parser("serve", help="serve a local read-only HTTP view")
    server.add_argument("--world", type=Path)
    server.add_argument("--run", type=Path)
    server.add_argument("--evidence", type=Path)
    server.add_argument("--events", type=Path)
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8787)
    server.add_argument("--studio", type=Path, help="Studio HTML document; defaults to the repository copy or SFC_STUDIO_PATH")

    # Grouped command families are additive aliases over the stable flat CLI.
    # The flat commands remain supported so scripts and published examples do
    # not break while the domain vocabulary matures.
    project = sub.add_parser("project", help="project-state commands")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_inspect = project_sub.add_parser("inspect", help="inspect a Project World")
    project_inspect.add_argument("project_world", type=Path)

    requirements = sub.add_parser("requirements", help="requirement and determination commands")
    requirements_sub = requirements.add_subparsers(dest="requirements_command", required=True)
    requirements_check = requirements_sub.add_parser("check", help="evaluate an obligation against a Project World")
    requirements_check.add_argument("requirement", type=Path)
    requirements_check.add_argument("project_world", type=Path)
    requirements_check.add_argument("--output", type=Path, default=Path(".sfc/last-run.json"))
    requirements_check.add_argument("--store", type=Path, default=Path(".sfc"))
    _add_vocabulary_option(requirements_check)

    work = sub.add_parser("work", help="inspect governed Work Unit contracts")
    work_sub = work.add_subparsers(dest="work_command", required=True)
    work_inspect = work_sub.add_parser("inspect", help="inspect and normalize a Work Unit JSON document")
    work_inspect.add_argument("work_unit", type=Path)

    ai = sub.add_parser("ai", help="engineering-intelligence commands")
    ai_sub = ai.add_subparsers(dest="ai_command", required=True)
    ai_investigate = ai_sub.add_parser("investigate", help="run a bounded requirement investigation")
    ai_investigate.add_argument("source", type=Path)
    ai_investigate.add_argument("--statement", required=True)
    ai_investigate.add_argument("--output", type=Path, default=Path(".sfc/investigation.json"))
    ai_investigate.add_argument("--store", type=Path, default=Path(".sfc"))
    ai_investigate.add_argument("--provider", choices=["reference", "environment"], default="reference")
    _add_vocabulary_option(ai_investigate)

    plugins = sub.add_parser("plugins", help="inspect SFC plugin manifests")
    plugins_sub = plugins.add_subparsers(dest="plugins_command", required=True)
    plugins_list = plugins_sub.add_parser("list", help="list plugin manifests in a directory")
    plugins_list.add_argument("--path", type=Path, default=Path(".sfc/plugins"))
    plugins_inspect = plugins_sub.add_parser("inspect", help="inspect and validate a plugin manifest")
    plugins_inspect.add_argument("manifest", type=Path)

    gateway = sub.add_parser("gateway", help="serve the local SFC AI Gateway")
    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, default=8790)
    gateway.add_argument("--ledger", type=Path, default=Path(".sfc/gateway-usage.jsonl"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        # A missing file or an unevaluable obligation is a usage problem, not a
        # crash. The traceback is noise to someone running a command.
        print(f"sfc: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


def _dispatch(args: argparse.Namespace) -> int:
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
    if args.command == "readiness":
        return _readiness(args)
    if args.command == "vocabulary":
        return _vocabulary_command(args)
    if args.command == "serve":
        serve(args.world, args.run, args.host, args.port, evidence_path=args.evidence, event_path=args.events, studio=args.studio)
        return 0
    if args.command == "project":
        if args.project_command == "inspect":
            return _inspect(args)
    if args.command == "requirements":
        if args.requirements_command == "check":
            return _verify(args)
    if args.command == "work":
        if args.work_command == "inspect":
            return _work_inspect(args)
    if args.command == "ai":
        if args.ai_command == "investigate":
            return _investigate(args)
    if args.command == "plugins":
        return _plugins(args)
    if args.command == "gateway":
        serve_gateway(host=args.host, port=args.port, ledger_path=args.ledger)
        return 0
    return 2


def _work_inspect(args: argparse.Namespace) -> int:
    work = WorkUnit.from_dict(read_json(args.work_unit))
    print(json.dumps(work.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _plugins(args: argparse.Namespace) -> int:
    if args.plugins_command == "list":
        manifests = [manifest.to_dict() for manifest in discover_plugin_manifests(args.path)]
        print(json.dumps({"plugins": manifests, "count": len(manifests)}, ensure_ascii=False, indent=2))
        return 0
    if args.plugins_command == "inspect":
        manifest = PluginManifest.from_dict(read_json(args.manifest))
        print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))
        return 0
    return 2


def _verify(args: argparse.Namespace) -> int:
    obligation = load_obligation(args.requirement)
    world = load_world(args.project_world)
    store = RunStore(args.store)
    frozen = store.freeze(world, obligation)
    determination = evaluate_obligation(obligation, world, vocabulary=_vocabulary(args))
    run = create_run(world, frozen, determination)
    path = store.publish(run)
    output = run.to_dict()
    write_json(args.output, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Published {run.run_id} to {path}")
    return 0 if determination.status in CLOSING_STATUSES else 1


def _inspect(args: argparse.Namespace) -> int:
    world = load_world(args.project_world)
    by_kind: dict[str, int] = {}
    for element in world.elements:
        by_kind[element.kind] = by_kind.get(element.kind, 0) + 1
    print(json.dumps({"projectId": world.project_id, "elements": len(world.elements), "byKind": by_kind, "snapshotHash": world.snapshot_hash()}, indent=2))
    return 0


def _doctor(args: argparse.Namespace) -> int:
    store = RunStore(args.store)
    print(json.dumps({
        "status": "ok",
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "store": str(store.root),
        "canonicalRun": store.load_canonical() is not None,
        "vocabulary": _vocabulary(args).vocabulary_id,
    }, indent=2))
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
    publication = investigate_and_publish(world, args.statement, store=RunStore(args.store), provider=provider, vocabulary=_vocabulary(args))
    result = {
        "agent": {"agentId": publication.agent.agent_id, "actions": publication.agent.actions, "terminalReason": publication.agent.terminal_reason, "findings": [{"statement": finding.statement, "evidenceIds": list(finding.evidence_ids)} for finding in publication.agent.findings]},
        "admittedEvidence": [item.to_dict() for item in publication.admitted_evidence],
        "proof": publication.proof.to_dict(),
        "run": publication.run.to_dict(),
    }
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if publication.determination.status in CLOSING_STATUSES else 1


def _bench(args: argparse.Namespace) -> int:
    result = run_benchmark(args.fixture, vocabulary=_vocabulary(args))
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["metrics"].get("accuracy", 1.0) in {1.0, "not_scored_without_fixture_truth"} else 1


def _vocabulary_command(args: argparse.Namespace) -> int:
    vocabulary = _vocabulary(args)
    print(json.dumps(vocabulary.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _report(args: argparse.Namespace) -> int:
    destination = write_report(args.run, args.output, args.format)
    print(destination)
    return 0


def _readiness(args: argparse.Namespace) -> int:
    determinations = []
    for path in args.runs:
        document = read_json(path)
        run_document = document.get("run", document)
        determinations.append(Determination.from_dict(run_document.get("determination", run_document)))
    evidence: list[Evidence] = []
    if args.evidence:
        source = read_json(args.evidence)
        records = source if isinstance(source, list) else source.get("admitted", source.get("evidence", [source]))
        evidence = [Evidence.from_dict(item) for item in records]
    else:
        for path in args.runs:
            document = read_json(path)
            evidence.extend(Evidence.from_dict(item) for item in document.get("admittedEvidence", []))
    result = compute_readiness(tuple(determinations), evidence).to_dict()
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
