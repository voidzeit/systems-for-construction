"""Deterministic requirement evaluation and quantifier semantics."""

from __future__ import annotations

from operator import eq, ge, gt, le, lt, ne
from typing import Any, Callable

from .models import (
    Counterexample,
    Determination,
    DeterminationStatus,
    Obligation,
    ProjectWorld,
    Quantifier,
)


OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": eq,
    "!=": ne,
    ">=": ge,
    ">": gt,
    "<=": le,
    "<": lt,
}


class AssuranceError(ValueError):
    """Raised when a determination violates an SFC invariant."""


def validate_determination(determination: Determination) -> None:
    if determination.expected_population < 0 or determination.evaluated_population < 0:
        raise AssuranceError("population counts cannot be negative")
    if determination.evaluated_population > determination.expected_population:
        raise AssuranceError("evaluated population cannot exceed expected population")
    if determination.conforming > determination.evaluated_population:
        raise AssuranceError("conforming count cannot exceed evaluated population")
    if not 0 <= determination.coverage <= 1:
        raise AssuranceError("coverage must be between 0 and 1")
    if determination.status is DeterminationStatus.MET:
        if determination.evaluated_population != determination.expected_population:
            raise AssuranceError("MET requires complete population coverage")
        if determination.counterexamples or determination.unknowns:
            raise AssuranceError("MET cannot contain counterexamples or unknowns")
    if determination.status is DeterminationStatus.NOT_MET and not determination.counterexamples and determination.quantifier is Quantifier.ALL:
        raise AssuranceError("ALL/NOT_MET requires a counterexample")


def _matches_population(element: Any, population: dict[str, Any]) -> bool:
    if population.get("kind") and element.kind != population["kind"]:
        return False
    for key, expected in population.get("where", {}).items():
        if element.properties.get(key) != expected:
            return False
    return True


def _check_predicate(observed: Any, predicate: dict[str, Any]) -> bool:
    operator = predicate.get("operator", "==")
    if operator not in OPERATORS:
        raise ValueError(f"unsupported predicate operator: {operator}")
    return OPERATORS[operator](observed, predicate.get("value"))


def evaluate_obligation(obligation: Obligation, world: ProjectWorld) -> Determination:
    population = [element for element in world.elements if _matches_population(element, obligation.population)]
    property_name = obligation.predicate.get("property")
    expected = obligation.predicate.get("value")
    evaluated = 0
    conforming = 0
    evidence_ids: list[str] = []
    unknowns: list[str] = []
    counterexamples: list[Counterexample] = []

    for element in population:
        if property_name not in element.properties or element.properties[property_name] is None:
            unknowns.append(element.element_id)
            continue
        observed = element.properties[property_name]
        evaluated += 1
        element_evidence = tuple(element.evidence_by_property.get(property_name, ()))
        evidence_ids.extend(element_evidence)
        try:
            conforms = _check_predicate(observed, obligation.predicate)
        except (TypeError, ValueError) as error:
            unknowns.append(f"{element.element_id}: {error}")
            evaluated -= 1
            continue
        if conforms:
            conforming += 1
        else:
            counterexamples.append(
                Counterexample(
                    subject=element.element_id,
                    observed=observed,
                    expected=f"{obligation.predicate.get('operator', '==')} {expected}",
                    evidence_ids=element_evidence,
                    reason=f"property {property_name} does not satisfy predicate",
                )
            )

    expected_population = len(population)
    coverage = evaluated / expected_population if expected_population else 1.0
    status = _determine_status(
        obligation.quantifier,
        expected_population,
        evaluated,
        conforming,
        bool(counterexamples),
        bool(unknowns),
        obligation.predicate,
    )
    return Determination(
        requirement_id=obligation.requirement.requirement_id,
        obligation_id=obligation.obligation_id,
        quantifier=obligation.quantifier,
        expected_population=expected_population,
        evaluated_population=evaluated,
        conforming=conforming,
        coverage=round(coverage, 6),
        status=status,
        counterexamples=tuple(counterexamples),
        evidence_ids=tuple(dict.fromkeys(evidence_ids)),
        unknowns=tuple(unknowns),
        assumptions=tuple(obligation.population.get("assumptions", [])),
        rule_set_version=obligation.rule_set_version,
    )


def _determine_status(
    quantifier: Quantifier,
    expected: int,
    evaluated: int,
    conforming: int,
    has_counterexamples: bool,
    has_unknowns: bool,
    predicate: dict[str, Any],
) -> DeterminationStatus:
    if quantifier is Quantifier.ALL:
        if has_counterexamples:
            return DeterminationStatus.NOT_MET
        if has_unknowns or evaluated < expected:
            return DeterminationStatus.INCOMPLETE
        return DeterminationStatus.MET
    if quantifier is Quantifier.ANY:
        if conforming > 0:
            return DeterminationStatus.MET
        if has_unknowns or evaluated < expected:
            return DeterminationStatus.INCOMPLETE
        return DeterminationStatus.NOT_MET
    if quantifier is Quantifier.NONE:
        if conforming > 0:
            return DeterminationStatus.NOT_MET
        if has_unknowns or evaluated < expected:
            return DeterminationStatus.INCOMPLETE
        return DeterminationStatus.MET
    if quantifier is Quantifier.COUNT:
        minimum = predicate.get("minimum")
        maximum = predicate.get("maximum")
        if minimum is not None and conforming < minimum:
            return DeterminationStatus.NOT_MET if not has_unknowns else DeterminationStatus.INCOMPLETE
        if maximum is not None and conforming > maximum:
            return DeterminationStatus.NOT_MET
        if has_unknowns or evaluated < expected:
            return DeterminationStatus.INCOMPLETE
        return DeterminationStatus.MET
    raise ValueError(f"unsupported quantifier: {quantifier}")
