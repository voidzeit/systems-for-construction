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


if __name__ == "__main__":
    raise SystemExit(main())

