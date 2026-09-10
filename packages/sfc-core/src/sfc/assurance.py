"""Deterministic requirement evaluation and quantifier semantics."""

from __future__ import annotations

from operator import eq, ge, gt, le, lt, ne
from typing import Any, Callable
import re

from .models import (
    CLOSING_STATUSES,
    Counterexample,
    Determination,
    DeterminationReason,
    DeterminationStatus,
    EmptyPopulationPolicy,
    Obligation,
    PopulationSpec,
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
    if determination.coverage is None:
        if determination.expected_population:
            raise AssuranceError("coverage is required when a population exists")
    elif not 0 <= determination.coverage <= 1:
        raise AssuranceError("coverage must be between 0 and 1")
    if determination.status is DeterminationStatus.MET:
        if determination.expected_population == 0:
            raise AssuranceError("MET requires a non-empty population; absence is not compliance")
        if determination.evaluated_population != determination.expected_population:
            raise AssuranceError("MET requires complete population coverage")
        if determination.counterexamples or determination.unknowns:
            raise AssuranceError("MET cannot contain counterexamples or unknowns")
    if determination.status is DeterminationStatus.NOT_APPLICABLE:
        if determination.expected_population:
            raise AssuranceError("NOT_APPLICABLE requires an empty population")
        if not determination.evidence_ids:
            raise AssuranceError("NOT_APPLICABLE requires evidence that the requirement does not apply")
        if determination.counterexamples or determination.unknowns:
            raise AssuranceError("NOT_APPLICABLE cannot contain counterexamples or unknowns")
    if determination.status is DeterminationStatus.NOT_MET and not determination.counterexamples and determination.quantifier is Quantifier.ALL:
        raise AssuranceError("ALL/NOT_MET requires a counterexample")


def _matches_population(element: Any, spec: PopulationSpec) -> bool:
    aliases = {
        "electrical_panel": {"electrical_panel", "electricdistributionboard", "electrical_distribution_board"},
        "electricdistributionboard": {"electrical_panel", "electricdistributionboard", "electrical_distribution_board"},
        "electrical_distribution_board": {"electrical_panel", "electricdistributionboard", "electrical_distribution_board"},
    }
    if spec.kind and element.kind not in aliases.get(spec.kind, {spec.kind}):
        return False
    for key, expected in spec.where.items():
        if element.properties.get(key) != expected:
            return False
    return True


def resolve_property(element: Any, requested: str) -> tuple[str, Any] | None:
    if requested in element.properties:
        return requested, element.properties[requested]
    normalize = lambda value: re.sub(r"[^a-z0-9]", "", value.lower())
    wanted = normalize(requested).removesuffix("inches")
    for name, value in element.properties.items():
        if normalize(name).removesuffix("inches") == wanted:
            return name, value
    return None


def _check_predicate(observed: Any, predicate: dict[str, Any]) -> bool:
    operator = predicate.get("operator", "==")
    if operator not in OPERATORS:
        raise ValueError(f"unsupported predicate operator: {operator}")
    return OPERATORS[operator](observed, predicate.get("value"))


def _empty_population_determination(obligation: Obligation, spec: PopulationSpec) -> Determination:
    """An empty population may close only when non-applicability is itself evidenced.

    Zero matched subjects is ambiguous: the requirement may genuinely not apply,
    or the discipline was never loaded, or the kind is misspelled, or the
    connector dropped that family of elements. SFC cannot tell those apart from
    the snapshot alone, so it refuses to read absence as compliance.
    """
    if spec.applicability.proven_not_applicable:
        status = DeterminationStatus.NOT_APPLICABLE
        reasons: tuple[str, ...] = (DeterminationReason.NOT_APPLICABLE_EVIDENCED.value,)
        evidence_ids = spec.applicability.evidence_ids
    else:
        status = DeterminationStatus.INCOMPLETE
        evidence_ids = ()
        if spec.empty_population_policy is EmptyPopulationPolicy.NOT_APPLICABLE:
            reasons = (DeterminationReason.EMPTY_POPULATION_APPLICABILITY_UNEVIDENCED.value,)
        else:
            reasons = (DeterminationReason.EMPTY_POPULATION_UNRESOLVED.value,)
        if spec.minimum_expected:
            reasons += (DeterminationReason.POPULATION_BELOW_MINIMUM.value,)
    return Determination(
        requirement_id=obligation.requirement.requirement_id,
        obligation_id=obligation.obligation_id,
        quantifier=obligation.quantifier,
        expected_population=0,
        evaluated_population=0,
        conforming=0,
        coverage=None,
        status=status,
        evidence_ids=tuple(evidence_ids),
        assumptions=tuple(spec.assumptions),
        reasons=reasons,
        applicability=spec.applicability.to_dict(),
        rule_set_version=obligation.rule_set_version,
    )


def evaluate_obligation(obligation: Obligation, world: ProjectWorld) -> Determination:
    spec = PopulationSpec.from_dict(obligation.population)
    population = [element for element in world.elements if _matches_population(element, spec)]
    if not population:
        return _empty_population_determination(obligation, spec)

    property_name = obligation.predicate.get("property")
    expected = obligation.predicate.get("value")
    evaluated = 0
    conforming = 0
    evidence_ids: list[str] = []
    unknowns: list[str] = []
    reasons: list[str] = []
    counterexamples: list[Counterexample] = []

    for element in population:
        resolved = resolve_property(element, property_name)
        if resolved is None or resolved[1] is None:
            unknowns.append(element.element_id)
            if DeterminationReason.MISSING_OBSERVATION.value not in reasons:
                reasons.append(DeterminationReason.MISSING_OBSERVATION.value)
            continue
        actual_property, observed = resolved
        element_evidence = tuple(element.evidence_by_property.get(actual_property, element.evidence_by_property.get(property_name, ())))
        try:
            conforms = _check_predicate(observed, obligation.predicate)
        except (TypeError, ValueError) as error:
            unknowns.append(f"{element.element_id}: {error}")
            if DeterminationReason.PREDICATE_NOT_EVALUABLE.value not in reasons:
                reasons.append(DeterminationReason.PREDICATE_NOT_EVALUABLE.value)
            continue
        # Evidence is cited only once the subject was actually evaluated, so a
        # determination never rests on evidence for a subject it could not decide.
        evaluated += 1
        evidence_ids.extend(element_evidence)
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
    below_minimum = expected_population < spec.minimum_expected
    if below_minimum:
        reasons.append(DeterminationReason.POPULATION_BELOW_MINIMUM.value)
    coverage = evaluated / expected_population
    status = _determine_status(
        obligation.quantifier,
        expected_population,
        evaluated,
        conforming,
        bool(counterexamples),
        bool(unknowns),
        obligation.predicate,
        below_minimum,
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
        assumptions=tuple(spec.assumptions),
        reasons=tuple(reasons),
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
    below_minimum: bool = False,
) -> DeterminationStatus:
    status = _quantifier_status(quantifier, expected, evaluated, conforming, has_counterexamples, has_unknowns, predicate)
    # A population smaller than the requirement presupposes cannot close, even
    # when every subject that was found conforms.
    if below_minimum and status in CLOSING_STATUSES and status is not DeterminationStatus.NOT_MET:
        return DeterminationStatus.INCOMPLETE
    return status


def _quantifier_status(
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
