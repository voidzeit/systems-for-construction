"""Usage ledger where unavailable measurements remain absent."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .models import _utc_now


class UsageLedger:
    def __init__(self, path: str | Path = ".sfc/usage.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, **fields: Any) -> None:
        # None means unavailable. It is deliberately omitted instead of becoming zero.
        payload = {key: value for key, value in fields.items() if value is not None}
        payload.setdefault("recordedAt", _utc_now())
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

