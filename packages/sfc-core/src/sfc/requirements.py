"""Deterministic compiler for a small, explicit natural-language subset."""

from __future__ import annotations

from typing import Any
import re

from .models import Obligation, Quantifier, Requirement
from .quantities import UnknownUnitError, resolve_unit


class RequirementCompilationError(ValueError):
    pass


PATTERNS = (
    re.compile(r"^(?:every|all)\s+(?P<subject>.+?)\s+must\s+(?:maintain|have|provide)\s+(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>inches?|in\.?|mm|meters?|m)?\s*(?:of\s+)?(?P<property>[a-z][a-z _-]*)\.?$", re.IGNORECASE),
    re.compile(r"^(?:every|all)\s+(?P<subject>.+?)\s+must\s+have\s+(?P<property>[a-z][a-z _-]*)\s*(?P<operator>>=|<=|==|!=|>|<)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>.*)$", re.IGNORECASE),
)


def _kind(subject: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", subject.lower()).strip("_")
    aliases = {
        "electrical_panel": "electrical_panel",
        "electrical_panels": "electrical_panel",
        "electric_panel": "electrical_panel",
        "electric_distribution_board": "electricdistributionboard",
        "electric_distribution_boards": "electricdistributionboard",
    }
    return aliases.get(normalized, normalized.rstrip("s"))


def _property(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return normalized


def compile_requirement(statement: str, *, requirement_id: str = "REQ-COMPILED-001", title: str | None = None) -> Obligation:
    text = " ".join(statement.strip().split())
    match = next((pattern.match(text.rstrip(".")) for pattern in PATTERNS if pattern.match(text.rstrip("."))), None)
    if not match:
        raise RequirementCompilationError("unsupported requirement; use 'Every <subject> must maintain <number> inches of <property>' or an explicit comparison")
    groups = match.groupdict()
    subject = _kind(groups["subject"])
    property_name = _property(groups["property"])
    value = float(groups["value"])
    if value.is_integer():
        value = int(value)
    operator = groups.get("operator") or ">="
    try:
        unit = resolve_unit(groups.get("unit"))
    except UnknownUnitError as error:
        # The controlled language refuses rather than guessing what was meant.
        raise RequirementCompilationError(str(error)) from error
    requirement = Requirement(requirement_id, title or text, text)
    predicate: dict[str, Any] = {"property": property_name, "operator": operator, "value": value}
    if unit is not None:
        # The unit belongs to the measurement, never to the property name.
        predicate["unit"] = unit
    return Obligation(
        obligation_id=f"OBL-{requirement_id}",
        requirement=requirement,
        quantifier=Quantifier.ALL,
        population={"kind": subject, "minimumExpected": 1},
        predicate=predicate,
    )

