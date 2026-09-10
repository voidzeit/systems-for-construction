"""Compiler for a controlled requirement language.

This is not a general natural-language compiler. It accepts a small, explicit
set of sentence forms and refuses everything else, so a requirement is never
turned into an obligation by interpretation. Widening the accepted input is a
deliberate change to the grammar, not a model choice at runtime.
"""

from __future__ import annotations

from typing import Any
import re

from .models import Obligation, Quantifier, Requirement
from .quantities import UnknownUnitError, resolve_unit
from .vocabulary import Vocabulary, normalize


class RequirementCompilationError(ValueError):
    pass


PATTERNS = (
    re.compile(r"^(?:every|all)\s+(?P<subject>.+?)\s+must\s+(?:maintain|have|provide)\s+(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>inches?|in\.?|mm|meters?|m)?\s*(?:of\s+)?(?P<property>[a-z][a-z _-]*)\.?$", re.IGNORECASE),
    re.compile(r"^(?:every|all)\s+(?P<subject>.+?)\s+must\s+have\s+(?P<property>[a-z][a-z _-]*)\s*(?P<operator>>=|<=|==|!=|>|<)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>.*)$", re.IGNORECASE),
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _kind(subject: str, vocabulary: Vocabulary) -> str:
    """Resolve the subject to a canonical kind, falling back to its own slug.

    Plural handling is grammar, not domain knowledge, so it stays here. Which
    spellings denote the same equipment is a domain claim and lives in the pack.
    """
    for candidate in (_slug(subject), _slug(subject).removesuffix("s")):
        resolved = vocabulary.resolve_kind(candidate)
        if resolved != normalize(candidate):
            return resolved
    return _slug(subject).removesuffix("s")


def _property(name: str, vocabulary: Vocabulary) -> str:
    slug = _slug(name)
    resolved = vocabulary.resolve_property(slug)
    return resolved if resolved != normalize(slug) else slug


def compile_requirement(
    statement: str,
    *,
    requirement_id: str = "REQ-COMPILED-001",
    title: str | None = None,
    vocabulary: Vocabulary | None = None,
) -> Obligation:
    vocabulary = vocabulary or Vocabulary.empty()
    text = " ".join(statement.strip().split())
    match = next((pattern.match(text.rstrip(".")) for pattern in PATTERNS if pattern.match(text.rstrip("."))), None)
    if not match:
        raise RequirementCompilationError("unsupported requirement; use 'Every <subject> must maintain <number> inches of <property>' or an explicit comparison")
    groups = match.groupdict()
    subject = _kind(groups["subject"], vocabulary)
    property_name = _property(groups["property"], vocabulary)
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

