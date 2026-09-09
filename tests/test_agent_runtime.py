import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from sfc.agent_runtime import AgentRuntime
from sfc.agents import AgentPolicy
from sfc.providers import ProviderRequest, ProviderResponse
from sfc.telemetry import UsageLedger


class FakeProvider:
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse("candidate observation", "fake", "fake", None, 7)


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

