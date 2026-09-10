"""Complete local investigation path from natural language to canonical run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re

from .agent_runtime import AgentRuntime, InvestigationResult, RegisteredTool, ToolObservation
from .agents import AgentPolicy
from .assurance import evaluate_obligation, observe_measurement, resolve_property
from .authority import EvidenceAuthority
from .models import Evidence, EvidenceSourceType, Obligation, ProjectWorld, Determination, Run
from .proofs import Proof
from .requirements import compile_requirement
from .runtime import RunStore, create_run
from .providers import EngineeringProvider
from .vocabulary import Vocabulary, default_vocabulary


class ReferenceInvestigationProvider:
    """Deterministic provider used for offline demos and regression tests."""

    def __init__(self, property_name: str):
        self.property_name = property_name

    def complete(self, request):
        from .providers import ProviderResponse, ToolCall
        prompt = request.prompt
        if "- project.search:" not in prompt:
            return ProviderResponse("", "sfc-reference", "sfc-reference", tool_calls=(ToolCall("search", "project.search", {"query": ""}),))
        if "- element.get:" not in prompt:
            ids = re.findall(r"'elementId': '([^']+)'|\"elementId\": \"([^\"]+)\"", prompt)
            element_id = next((left or right for left, right in ids), None)
            if element_id:
                return ProviderResponse("", "sfc-reference", "sfc-reference", tool_calls=(ToolCall("get", "element.get", {"elementId": element_id}),))
        if "- geometry.measure:" not in prompt:
            ids = re.findall(r"'elementId': '([^']+)'|\"elementId\": \"([^\"]+)\"", prompt)
            element_id = next((left or right for left, right in ids), None)
            if element_id:
                return ProviderResponse("", "sfc-reference", "sfc-reference", tool_calls=(ToolCall("measure", "geometry.measure", {"elementId": element_id, "property": self.property_name}),))
        return ProviderResponse("Investigation completed from Project World observations.", "sfc-reference", "sfc-reference")


@dataclass(frozen=True)
class InvestigationPublication:
    obligation: Obligation
    agent: InvestigationResult
    admitted_evidence: tuple[Evidence, ...]
    determination: Determination
    proof: Proof
    run: Run


def _tools_for(world: ProjectWorld, property_name: str, vocabulary: Vocabulary) -> dict[str, RegisteredTool]:
    def search(arguments):
        query = str(arguments.get("query", "")).lower()
        matches = [element.to_dict() for element in world.elements if not query or query in json.dumps(element.to_dict(), ensure_ascii=False).lower()]
        evidence = tuple(evidence_id for element in world.elements for evidence_ids in element.evidence_by_property.values() for evidence_id in evidence_ids if not query or query in json.dumps(element.to_dict(), ensure_ascii=False).lower())
        return ToolObservation("project.search", matches, evidence)

    def get_element(arguments):
        element = next((item for item in world.elements if item.element_id == arguments.get("elementId")), None)
        if element is None:
            return ToolObservation("element.get", {"error": "element not found"})
        return ToolObservation("element.get", element.to_dict(), tuple(evidence_id for ids in element.evidence_by_property.values() for evidence_id in ids))

    def measure(arguments):
        element = next((item for item in world.elements if item.element_id == arguments.get("elementId")), None)
        if element is None:
            return ToolObservation("geometry.measure", {"error": "element not found"})
        requested = arguments.get("property")
        resolved = resolve_property(element, requested, vocabulary)
        value = resolved[1] if resolved else element.geometry.get(requested)
        evidence = tuple(element.evidence_by_property.get(resolved[0] if resolved else requested, ()))
        return ToolObservation("geometry.measure", {"elementId": element.element_id, "property": arguments.get("property"), "value": value}, evidence)

    return {
        "project.search": RegisteredTool("project.search", "project_world", search, "Search Project World elements", {"type": "object", "properties": {"query": {"type": "string"}}}),
        "element.get": RegisteredTool("element.get", "project_world", get_element, "Get an element", {"type": "object", "properties": {"elementId": {"type": "string"}}}),
        "geometry.measure": RegisteredTool("geometry.measure", "project_world", measure, "Read a stored measurement", {"type": "object", "properties": {"elementId": {"type": "string"}, "property": {"type": "string"}}}),
    }


def investigate_and_publish(world: ProjectWorld, statement: str, *, store: RunStore | None = None, requirement_id: str = "REQ-COMPILED-001", provider: EngineeringProvider | None = None, vocabulary: Vocabulary | None = None) -> InvestigationPublication:
    vocabulary = vocabulary if vocabulary is not None else default_vocabulary()
    obligation = compile_requirement(statement, requirement_id=requirement_id, vocabulary=vocabulary)
    policy = AgentPolicy.from_dict({"agent": {"id": "sfc-reference-engineer", "capabilities": {"read": ["project_world"], "propose": ["evidence_claim", "verification"], "write": []}, "limits": {"maxActions": 8, "maxRuntimeSeconds": 60}, "authority": {"mayPublish": False, "mayApprove": False}}})
    selected_provider = provider or ReferenceInvestigationProvider(obligation.predicate["property"])
    agent = AgentRuntime(policy, selected_provider, _tools_for(world, obligation.predicate["property"], vocabulary)).investigate(statement)
    determination = evaluate_obligation(obligation, world, vocabulary=vocabulary)
    authority = EvidenceAuthority()
    admitted = []
    for element in world.elements:
        resolved = resolve_property(element, obligation.predicate["property"], vocabulary)
        if resolved is None:
            continue
        actual_property, actual_value = resolved
        evidence_id = element.evidence_by_property.get(actual_property, (f"world:{element.element_id}:{actual_property}",))[0]
        admitted.append(authority.admit(Evidence(
            evidence_id,
            element.source_id or world.project_id,
            EvidenceSourceType.MODEL_ELEMENT,
            {"elementId": element.element_id, "property": actual_property},
            actual_value,
            0.8,
            1.0,
            ("project-world", f"snapshot:{world.snapshot_hash()}"),
            measurement=observe_measurement(actual_value, obligation),
        )))
    proof = Proof.from_determination(determination)
    run_store = store or RunStore()
    frozen = run_store.freeze(world, obligation)
    run = create_run(world, frozen, determination, evidence_ids=tuple(item.evidence_id for item in admitted), proof=proof.to_dict())
    run_store.publish(run)
    return InvestigationPublication(obligation, agent, tuple(admitted), determination, proof, run)
