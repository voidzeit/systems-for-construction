"""Small, dependency-free IFC STEP connector.

This is intentionally a conservative reader for common IFC entities and
single-value property sets. It preserves the raw source locator and creates a
ProjectWorld snapshot; unsupported IFC constructs remain outside the snapshot
instead of being guessed.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
import hashlib
import re

from .models import ProjectWorld, WorldElement


ENTITY_RE = re.compile(r"#(?P<id>\d+)\s*=\s*(?P<kind>[A-Z0-9_]+)\s*\((?P<body>.*?)\)\s*;", re.IGNORECASE | re.DOTALL)
REF_RE = re.compile(r"#(\d+)")
STRING_RE = re.compile(r"'((?:''|[^'])*)'")
PROPERTY_VALUE_RE = re.compile(r"\.?(?:IFCINTEGER|IFCREAL|IFCNUMBER|IFCBOOLEAN|IFCLOGICAL|IFCTEXT|IFCLABEL)\s*\((.*?)\)", re.IGNORECASE | re.DOTALL)

ELEMENT_KINDS = {
    "IFCWALL", "IFCWALLSTANDARDCASE", "IFCDOOR", "IFCWINDOW", "IFCSLAB",
    "IFCCOLUMN", "IFCBEAM", "IFCSPACE", "IFCFURNISHINGELEMENT",
    "IFCBUILDINGELEMENTPROXY", "IFCELECTRICDISTRIBUTIONBOARD",
    "IFCELECTRICAPPLIANCE", "IFCFLOWTERMINAL", "IFCFLOWSEGMENT",
}


def _unquote(value: str) -> str:
    return value.replace("''", "'")


def _value(entity_body: str) -> Any:
    match = PROPERTY_VALUE_RE.search(entity_body)
    if not match:
        return None
    raw = match.group(1).strip()
    if raw.startswith("'") and raw.endswith("'"):
        return _unquote(raw[1:-1])
    if raw.upper() in {".T.", ".TRUE."}:
        return True
    if raw.upper() in {".F.", ".FALSE."}:
        return False
    try:
        return float(raw) if any(character in raw for character in ".E") else int(raw)
    except ValueError:
        return raw


def parse_ifc_text(text: str, source_id: str = "ifc-source") -> ProjectWorld:
    entities = {match.group("id"): (match.group("kind").upper(), match.group("body")) for match in ENTITY_RE.finditer(text)}
    project_id = source_id
    for kind, body in entities.values():
        if kind == "IFCPROJECT":
            strings = STRING_RE.findall(body)
            if strings:
                project_id = _unquote(strings[0]) or source_id
            break

    property_values: dict[str, tuple[str, Any]] = {}
    for entity_id, (kind, body) in entities.items():
        if kind != "IFCPROPERTYSINGLEVALUE":
            continue
        strings = STRING_RE.findall(body)
        if strings:
            property_values[entity_id] = (_unquote(strings[0]), _value(body))

    properties_by_element: dict[str, dict[str, Any]] = {}
    evidence_by_element: dict[str, dict[str, list[str]]] = {}
    for kind, body in entities.values():
        if kind != "IFCRELDEFINESBYPROPERTIES":
            continue
        refs = REF_RE.findall(body)
        if len(refs) < 2:
            continue
        property_set_id = refs[-1]
        property_refs = REF_RE.findall(entities.get(property_set_id, ("", ""))[1])
        for element_id in refs[:-1]:
            for property_ref in property_refs:
                if property_ref not in property_values:
                    continue
                name, value = property_values[property_ref]
                properties_by_element.setdefault(element_id, {})[name] = value
                evidence_by_element.setdefault(element_id, {}).setdefault(name, []).append(f"ifc:{element_id}:{name}")

    elements: list[WorldElement] = []
    for entity_id, (kind, body) in entities.items():
        if kind not in ELEMENT_KINDS:
            continue
        strings = STRING_RE.findall(body)
        element_id = _unquote(strings[0]) if strings else f"ifc-entity-{entity_id}"
        elements.append(WorldElement(
            element_id=element_id,
            kind=kind.removeprefix("IFC").lower(),
            properties=properties_by_element.get(entity_id, {}),
            evidence_by_property={key: tuple(value) for key, value in evidence_by_element.get(entity_id, {}).items()},
            source_id=source_id,
        ))
    return ProjectWorld(
        project_id=project_id,
        elements=tuple(elements),
        metadata={"connector": "sfc.ifc", "sourceId": source_id, "schema": "IFC STEP"},
    )


def load_ifc(path: str | Path) -> ProjectWorld:
    source = Path(path)
    data = source.read_bytes()
    source_id = f"ifc:{hashlib.sha256(data).hexdigest()[:16]}"
    return parse_ifc_text(data.decode("utf-8", errors="replace"), source_id)
