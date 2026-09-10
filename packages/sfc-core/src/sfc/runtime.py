"""Filesystem reference runtime with freeze, checkpoint and atomic publish."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import os
import tempfile
import uuid

from .models import Determination, ProjectWorld, Run, _hash, _utc_now
from .assurance import validate_determination
from .conformance import validate_semantics


@dataclass(frozen=True)
class FrozenInputs:
    project_id: str
    world_hash: str
    obligation_hash: str
    frozen_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "projectId": self.project_id,
            "worldHash": self.world_hash,
            "obligationHash": self.obligation_hash,
            "frozenAt": self.frozen_at,
        }


class RunStore:
    """A small durable store used by the CLI and as a reference adapter."""

    def __init__(self, root: str | Path = ".sfc") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.runs = self.root / "runs"
        self.runs.mkdir(exist_ok=True)
        self.canonical = self.root / "canonical-run.json"

    def freeze(self, world: ProjectWorld, obligation: Any) -> FrozenInputs:
        frozen = FrozenInputs(
            project_id=world.project_id,
            world_hash=world.snapshot_hash(),
            obligation_hash=_hash(obligation.to_dict()),
            frozen_at=_utc_now(),
        )
        self._atomic_json(self.root / "frozen-inputs.json", frozen.to_dict())
        return frozen

    def checkpoint(self, run_id: str, payload: dict[str, Any]) -> Path:
        destination = self.runs / run_id / "checkpoint.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_json(destination, {"runId": run_id, "savedAt": _utc_now(), **payload})
        return destination

    def publish(self, run: Run) -> Path:
        # Two layers, because a run can be assembled from parts this runtime
        # never produced: the determination's own invariants, then the document
        # invariants that relate its fields and require the proof to describe
        # the determination it travels with.
        validate_determination(run.determination)
        document = run.to_dict()
        validate_semantics("run.schema.json", document)
        run_dir = self.runs / run.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        run_path = run_dir / "run.json"
        self._atomic_json(run_path, document)
        # The canonical pointer is atomically replaced only after run.json is complete.
        self._atomic_json(self.canonical, document)
        return run_path

    def load_canonical(self) -> dict[str, Any] | None:
        if not self.canonical.exists():
            return None
        return json.loads(self.canonical.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_json(destination: Path, payload: dict[str, Any]) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def create_run(world: ProjectWorld, frozen: FrozenInputs, determination: Determination, *, evidence_ids: tuple[str, ...] = (), proof: dict[str, Any] | None = None) -> Run:
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    input_hash = _hash({"world": frozen.world_hash, "obligation": frozen.obligation_hash})
    return Run(
        run_id=run_id,
        project_id=world.project_id,
        input_hash=input_hash,
        determination=determination,
        evidence_ids=evidence_ids,
        proof=proof,
    )
