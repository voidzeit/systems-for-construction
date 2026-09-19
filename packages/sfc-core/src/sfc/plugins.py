"""Portable SFC plugin manifests and stdlib-only discovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
import json


class PluginFamily(StrEnum):
    CONNECTOR = "connector"
    DOMAIN_PACK = "domain_pack"
    ASSURANCE = "assurance"
    PRODUCTION = "production"
    GENERATIVE = "generative"
    INTELLIGENCE = "intelligence"


class AutonomyLevel(StrEnum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    A4 = "A4"
    A5 = "A5"
    A6 = "A6"


@dataclass(frozen=True)
class PluginCapability:
    capability_id: str
    risk_class: str
    maximum_autonomy: AutonomyLevel
    input_contract: str | None = None
    output_contract: str | None = None
    preconditions: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    minimum_authority: str | None = None
    acceptance_contract: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PluginCapability":
        capability_id = str(value.get("capabilityId", "")).strip()
        if not capability_id:
            raise ValueError("plugin capability requires capabilityId")
        risk = str(value.get("riskClass", "")).strip()
        if risk not in {"low", "medium", "high", "critical"}:
            raise ValueError(f"invalid riskClass: {risk!r}")
        return cls(
            capability_id=capability_id,
            risk_class=risk,
            maximum_autonomy=AutonomyLevel(value.get("maximumAutonomy", "A0")),
            input_contract=value.get("inputContract"),
            output_contract=value.get("outputContract"),
            preconditions=tuple(value.get("preconditions", [])),
            side_effects=tuple(value.get("sideEffects", [])),
            minimum_authority=value.get("minimumAuthority"),
            acceptance_contract=value.get("acceptanceContract"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilityId": self.capability_id,
            "inputContract": self.input_contract,
            "outputContract": self.output_contract,
            "preconditions": list(self.preconditions),
            "sideEffects": list(self.side_effects),
            "riskClass": self.risk_class,
            "minimumAuthority": self.minimum_authority,
            "maximumAutonomy": self.maximum_autonomy.value,
            "acceptanceContract": self.acceptance_contract,
        }


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    contract_version: str
    family: PluginFamily
    domain: str
    capabilities: tuple[PluginCapability, ...]
    permissions: tuple[str, ...]
    side_effects: tuple[str, ...]
    autonomy_ceiling: AutonomyLevel
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    evidence_contract: str | None = None
    acceptance_contract: str | None = None
    runtime_requirements: tuple[str, ...] = ()
    compatibility: tuple[str, ...] = ()
    data_rights_behavior: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PluginManifest":
        required = ("pluginId", "name", "version", "contractVersion", "family", "domain")
        missing = [field for field in required if not str(value.get(field, "")).strip()]
        if missing:
            raise ValueError(f"plugin manifest missing required fields: {', '.join(missing)}")
        capabilities = tuple(PluginCapability.from_dict(item) for item in value.get("capabilities", []))
        ceiling = AutonomyLevel(value.get("autonomyCeiling", "A0"))
        order = {level: index for index, level in enumerate(AutonomyLevel)}
        for capability in capabilities:
            if order[capability.maximum_autonomy] > order[ceiling]:
                raise ValueError(
                    f"capability {capability.capability_id} exceeds plugin autonomy ceiling {ceiling.value}"
                )
        return cls(
            plugin_id=str(value["pluginId"]),
            name=str(value["name"]),
            version=str(value["version"]),
            contract_version=str(value["contractVersion"]),
            family=PluginFamily(value["family"]),
            domain=str(value["domain"]),
            capabilities=capabilities,
            permissions=tuple(value.get("permissions", [])),
            side_effects=tuple(value.get("sideEffects", [])),
            autonomy_ceiling=ceiling,
            inputs=tuple(value.get("inputs", [])),
            outputs=tuple(value.get("outputs", [])),
            evidence_contract=value.get("evidenceContract"),
            acceptance_contract=value.get("acceptanceContract"),
            runtime_requirements=tuple(value.get("runtimeRequirements", [])),
            compatibility=tuple(value.get("compatibility", [])),
            data_rights_behavior=value.get("dataRightsBehavior"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pluginId": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "contractVersion": self.contract_version,
            "family": self.family.value,
            "domain": self.domain,
            "capabilities": [capability.to_dict() for capability in self.capabilities],
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "permissions": list(self.permissions),
            "sideEffects": list(self.side_effects),
            "autonomyCeiling": self.autonomy_ceiling.value,
            "evidenceContract": self.evidence_contract,
            "acceptanceContract": self.acceptance_contract,
            "runtimeRequirements": list(self.runtime_requirements),
            "compatibility": list(self.compatibility),
            "dataRightsBehavior": self.data_rights_behavior,
        }


def discover_plugin_manifests(path: str | Path) -> tuple[PluginManifest, ...]:
    root = Path(path)
    if not root.exists():
        return ()
    if not root.is_dir():
        raise ValueError(f"plugin path is not a directory: {root}")
    manifests: list[PluginManifest] = []
    for candidate in sorted(root.glob("*.json")):
        document = json.loads(candidate.read_text(encoding="utf-8"))
        manifests.append(PluginManifest.from_dict(document))
    ids = [manifest.plugin_id for manifest in manifests]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate pluginId in plugin directory")
    return tuple(manifests)
