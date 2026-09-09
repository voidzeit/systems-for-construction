"""Machine-enforced subset of the SFC agent contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class AgentPolicy:
    agent_id: str
    readable: frozenset[str]
    proposable: frozenset[str]
    writable: frozenset[str]
    max_cost_usd: float | None
    max_runtime_seconds: int | None
    max_actions: int | None
    may_publish: bool
    may_approve: bool

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AgentPolicy":
        agent = value.get("agent", value)
        capabilities = agent.get("capabilities", {})
        limits = agent.get("limits", {})
        authority = agent.get("authority", {})
        return cls(
            agent_id=agent["id"],
            readable=frozenset(capabilities.get("read", [])),
            proposable=frozenset(capabilities.get("propose", [])),
            writable=frozenset(capabilities.get("write", [])),
            max_cost_usd=limits.get("maxCostUsd"),
            max_runtime_seconds=limits.get("maxRuntimeSeconds"),
            max_actions=limits.get("maxActions"),
            may_publish=bool(authority.get("mayPublish", False)),
            may_approve=bool(authority.get("mayApprove", False)),
        )

    @classmethod
    def load(cls, path: str | Path) -> "AgentPolicy":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def can_read(self, resource: str) -> bool:
        return resource in self.readable

    def can_propose(self, proposal: str) -> bool:
        return proposal in self.proposable

    def can_write(self, resource: str) -> bool:
        return resource in self.writable

    def assert_can_publish(self) -> None:
        if not self.may_publish:
            raise PermissionError(f"agent {self.agent_id} may not publish")

    def assert_can_approve(self) -> None:
        if not self.may_approve:
            raise PermissionError(f"agent {self.agent_id} may not approve")

