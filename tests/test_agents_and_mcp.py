import json
from pathlib import Path
import unittest

from sfc.agents import AgentPolicy
from sfc.mcp import handle


ROOT = Path(__file__).parents[1]


class AgentAndMcpTests(unittest.TestCase):
    def test_agent_manifest_blocks_publication(self) -> None:
        policy = AgentPolicy.load(ROOT / "agents/manifests/evidence-verifier.json")
        self.assertTrue(policy.can_read("project_world"))
        self.assertTrue(policy.can_propose("verification"))
        self.assertFalse(policy.can_write("determination"))
        with self.assertRaises(PermissionError):
            policy.assert_can_publish()

    def test_mcp_exposes_read_only_tools(self) -> None:
        response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertTrue({"sfc.project.inspect", "sfc.run.get", "sfc.project.search", "sfc.element.get", "sfc.evidence.get"} <= names)
