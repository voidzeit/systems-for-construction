"""Provider-neutral bounded investigation loop.

The runtime accepts proposals from a provider and tool observations, but only
returns candidate findings. Publication remains the responsibility of the
deterministic SFC runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
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
class RegisteredTool:
    name: str
    resource: str
    handler: Callable[[dict[str, Any]], ToolObservation]
    description: str = ""
    input_schema: dict[str, Any] | None = None


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
    def __init__(self, policy: AgentPolicy, provider: InvestigationProvider, tools: dict[str, Callable[[dict[str, Any]], ToolObservation] | RegisteredTool], ledger: UsageLedger | None = None) -> None:
        self.policy = policy
        self.provider = provider
        self.tools = tools
        self.ledger = ledger

    def investigate(self, task: str, *, max_actions: int | None = None) -> InvestigationResult:
        started = time.monotonic()
        configured_limit = self.policy.max_actions if self.policy.max_actions is not None else 100
        requested_limit = configured_limit if max_actions is None else max(0, max_actions)
        action_limit = min(requested_limit, configured_limit)
        findings: list[CandidateFinding] = []
        actions = 0
        input_tokens = 0
        output_tokens = 0
        all_evidence_ids: list[str] = []
        transcript = task
        observation_history: list[ToolObservation] = []
        tool_specs = tuple(self._tool_spec(tool) for tool in self.tools.values())
        terminal_reason = "provider_completed"
        response = self.provider.complete(ProviderRequest(prompt=transcript, tools=tool_specs))
        while True:
            input_tokens += response.input_tokens or 0
            output_tokens += response.output_tokens or 0
            duration = time.monotonic() - started
            if self.policy.max_runtime_seconds is not None and duration > self.policy.max_runtime_seconds:
                terminal_reason = "runtime_limit_exceeded"
                findings.clear()
                break
            if not response.tool_calls:
                if self.policy.can_propose("evidence_claim") and response.text:
                    findings.append(CandidateFinding(response.text, tuple(dict.fromkeys(all_evidence_ids))))
                break
            next_observations: list[ToolObservation] = []
            for call in response.tool_calls:
                if actions >= action_limit:
                    terminal_reason = "action_limit_exceeded"
                    break
                actions += 1
                registered = self.tools.get(call.name)
                if registered is None:
                    next_observations.append(ToolObservation(call.name, {"error": "tool not registered"}))
                    continue
                tool = registered if isinstance(registered, RegisteredTool) else RegisteredTool(call.name, call.name, registered)
                if not self.policy.can_read(tool.resource):
                    next_observations.append(ToolObservation(call.name, {"error": f"agent cannot read {tool.resource}"}))
                    continue
                try:
                    next_observations.append(tool.handler(call.arguments))
                except Exception as error:  # tool errors become observations, never authority
                    next_observations.append(ToolObservation(call.name, {"error": str(error)}))
            if terminal_reason == "action_limit_exceeded":
                break
            observation_history.extend(next_observations)
            for observation in next_observations:
                all_evidence_ids.extend(observation.evidence_ids)
            transcript = f"{task}\n\nTool observations:\n{self._format_observations(observation_history)}\n\nContinue the investigation and return a grounded candidate finding when ready."
            response = self.provider.complete(ProviderRequest(prompt=transcript, tools=tool_specs))
        if self.ledger:
            self.ledger.record(invocationId=uuid.uuid4().hex, agentId=self.policy.agent_id, provider="configured", durationSeconds=duration, inputTokens=input_tokens or None, outputTokens=output_tokens or None, actions=actions, terminalReason=terminal_reason)
        return InvestigationResult(self.policy.agent_id, tuple(findings), actions, duration, terminal_reason)

    @staticmethod
    def _tool_spec(tool: Callable[[dict[str, Any]], ToolObservation] | RegisteredTool) -> dict[str, Any]:
        registered = tool if isinstance(tool, RegisteredTool) else RegisteredTool("tool", "tool", tool)
        return {"name": registered.name, "description": registered.description, "input_schema": registered.input_schema or {"type": "object"}}

    @staticmethod
    def _format_observations(observations: list[ToolObservation]) -> str:
        return "\n".join(f"- {observation.tool_name}: {observation.value}" for observation in observations)
