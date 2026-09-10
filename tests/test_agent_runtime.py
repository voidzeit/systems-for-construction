import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from sfc.agent_runtime import AgentRuntime, RegisteredTool, ToolObservation
from sfc.agents import AgentPolicy
from sfc.providers import ProviderRequest, ProviderResponse, ToolCall
from sfc.telemetry import UsageLedger


class FakeProvider:
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse("candidate observation", "fake", "fake", None, 7)


class MultiTurnProvider:
    def __init__(self):
        self.requests = []

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if len(self.requests) == 1:
            return ProviderResponse("", "fake", "fake", 2, 3, (ToolCall("call-1", "project.search", {"query": "panel"}),))
        return ProviderResponse("Panel LP-18 has a clearance issue.", "fake", "fake", 4, 5)


class AgentRuntimeTests(unittest.TestCase):
    def test_investigation_returns_candidate_and_records_unknown_usage_as_absent(self) -> None:
        policy = AgentPolicy.from_dict({"agent": {"id": "agent", "capabilities": {"propose": ["evidence_claim"], "write": []}, "limits": {"maxActions": 2}, "authority": {"mayPublish": False, "mayApprove": False}}})
        with TemporaryDirectory() as directory:
            ledger = UsageLedger(Path(directory) / "usage.jsonl")
            result = AgentRuntime(policy, FakeProvider(), {}, ledger).investigate("inspect panels")
            self.assertEqual(result.terminal_reason, "provider_completed")
            self.assertEqual(result.findings[0].statement, "candidate observation")
            record = ledger.read()[0]
            self.assertNotIn("inputTokens", record)
            self.assertEqual(record["outputTokens"], 7)

    def test_multi_turn_tool_call_returns_candidate_with_observed_evidence(self) -> None:
        policy = AgentPolicy.from_dict({"agent": {"id": "agent", "capabilities": {"read": ["project_world"], "propose": ["evidence_claim"], "write": []}, "limits": {"maxActions": 2}, "authority": {"mayPublish": False, "mayApprove": False}}})
        provider = MultiTurnProvider()
        tool = RegisteredTool("project.search", "project_world", lambda arguments: ToolObservation("project.search", [{"elementId": "LP-18"}], ("E-LP-18",)))
        result = AgentRuntime(policy, provider, {"project.search": tool}).investigate("find clearance issues")
        self.assertEqual(result.actions, 1)
        self.assertEqual(result.terminal_reason, "provider_completed")
        self.assertEqual(result.findings[0].evidence_ids, ("E-LP-18",))
        self.assertEqual(len(provider.requests), 2)

    def test_action_limit_is_enforced(self) -> None:
        policy = AgentPolicy.from_dict({"agent": {"id": "agent", "capabilities": {"read": ["project_world"], "propose": ["evidence_claim"], "write": []}, "limits": {"maxActions": 1}, "authority": {"mayPublish": False, "mayApprove": False}}})
        provider = MultiTurnProvider()
        tool = RegisteredTool("project.search", "project_world", lambda arguments: ToolObservation("project.search", [], ()))
        result = AgentRuntime(policy, provider, {"project.search": tool}).investigate("find clearance issues")
        self.assertEqual(result.actions, 1)
        self.assertEqual(result.terminal_reason, "provider_completed")
