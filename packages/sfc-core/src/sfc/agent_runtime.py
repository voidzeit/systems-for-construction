"""Provider-neutral bounded investigation loop.

The runtime accepts proposals from a provider and tool observations, but only
returns candidate findings. Publication remains the responsibility of the
deterministic SFC runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
import time
import uuid

from .agents import AgentPolicy
from .providers import ProviderRequest, ProviderResponse
from .telemetry import UsageLedger


class InvestigationProvider(Protocol):
    def complete(self, request: ProviderRequest) -> ProviderResponse: ...


@dataclass(frozen=True)
class ToolObservation:
    tool_name: str
    value: Any
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateFinding:
    statement: str
    evidence_ids: tuple[str, ...]
    source: str = "agent"


@dataclass(frozen=True)
class InvestigationResult:
    agent_id: str
    findings: tuple[CandidateFinding, ...]
    actions: int
    duration_seconds: float
    terminal_reason: str


class AgentRuntime:
    def __init__(self, policy: AgentPolicy, provider: InvestigationProvider, tools: dict[str, Callable[[dict[str, Any]], ToolObservation]], ledger: UsageLedger | None = None) -> None:
        self.policy = policy
        self.provider = provider
        self.tools = tools
        self.ledger = ledger

    def investigate(self, task: str, *, max_actions: int | None = None) -> InvestigationResult:
        started = time.monotonic()
        action_limit = min(max_actions or self.policy.max_actions or 100, self.policy.max_actions or 100)
        findings: list[CandidateFinding] = []
        actions = 0
        response = self.provider.complete(ProviderRequest(prompt=task))
        duration = time.monotonic() - started
        if self.policy.max_runtime_seconds is not None and duration > self.policy.max_runtime_seconds:
            if self.ledger:
                self.ledger.record(invocationId=uuid.uuid4().hex, agentId=self.policy.agent_id, provider="configured", durationSeconds=duration, inputTokens=response.input_tokens, outputTokens=response.output_tokens, terminalReason="runtime_limit_exceeded")
            return InvestigationResult(self.policy.agent_id, (), actions, duration, "runtime_limit_exceeded")
        if self.policy.can_propose("evidence_claim"):
            findings.append(CandidateFinding(response.text, ()))
        if self.ledger:
            self.ledger.record(invocationId=uuid.uuid4().hex, agentId=self.policy.agent_id, provider="configured", durationSeconds=duration, inputTokens=response.input_tokens, outputTokens=response.output_tokens, terminalReason="provider_completed")
        return InvestigationResult(self.policy.agent_id, tuple(findings), actions, duration, "provider_completed")
