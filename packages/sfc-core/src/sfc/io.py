"""Boundary helpers for portable JSON contracts."""

from pathlib import Path
from typing import Any, TypeVar
import json

from .models import Obligation, ProjectWorld

T = TypeVar("T")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_obligation(path: str | Path) -> Obligation:
    return Obligation.from_dict(read_json(path))


def load_world(path: str | Path) -> ProjectWorld:
    return ProjectWorld.from_dict(read_json(path))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
