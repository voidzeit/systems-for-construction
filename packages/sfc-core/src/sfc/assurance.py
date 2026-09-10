"""Deterministic requirement evaluation and quantifier semantics."""

from __future__ import annotations

from dataclasses import dataclass
from operator import eq, ge, gt, le, lt, ne
from typing import Any, Callable

from .quantities import (
    Conversion,
    MeasurementError,
    dimension_of,
    Quantity,
    DEFAULT_RELATIVE_TOLERANCE,
    compare_values,
    normalize_for_comparison,
    resolve_unit,
)
from .vocabulary import Vocabulary
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
    Unresolved,
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


def _matches_population(element: Any, spec: PopulationSpec, vocabulary: Vocabulary) -> bool:
    if spec.kind and vocabulary.resolve_kind(spec.kind) != vocabulary.resolve_kind(element.kind):
        return False
    for key, expected in spec.where.items():
        if element.properties.get(key) != expected:
            return False
    return True


def resolve_property(element: Any, requested: str, vocabulary: Vocabulary | None = None) -> tuple[str, Any] | None:
    """Find the observation an obligation is asking about.

    Punctuation and case are syntactic noise, so a name written in camel case
    resolves the same name written in snake case with no vocabulary at all.
    Anything beyond spelling - that a schedule column and a model property name
    denote the same measurement - is a domain assertion, and comes from the
    injected pack.
    """
    if requested in element.properties:
        return requested, element.properties[requested]
    vocabulary = vocabulary or Vocabulary.empty()
    wanted = vocabulary.resolve_property(requested)
    for name, value in element.properties.items():
        if vocabulary.resolve_property(name) == wanted:
            return name, value
    return None


@dataclass(frozen=True)
class MeasurementPolicy:
    """What an obligation permits when an observation carries no unit."""

    assumed_unit: str | None = None
    assumption_basis: str | None = None
    relative_tolerance: float = DEFAULT_RELATIVE_TOLERANCE

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "MeasurementPolicy":
        value = value or {}
        return cls(
            assumed_unit=resolve_unit(value.get("assumeObservedUnit")),
            assumption_basis=value.get("assumptionBasis"),
            relative_tolerance=float(value.get("relativeTolerance", DEFAULT_RELATIVE_TOLERANCE)),
        )


@dataclass(frozen=True)
class _Outcome:
    conforms: bool
    observed: Any
    expected: Any
    measurement: dict[str, Any] | None = None
    assumption: dict[str, Any] | None = None


def _evidence_for(element: Any, requested: str | None, resolved: str | None) -> tuple[str, ...]:
    """Evidence the element carries for the property under examination."""
    by_property = element.evidence_by_property
    for name in (resolved, requested):
        if name is not None and name in by_property:
            return tuple(by_property[name])
    return ()


def _check_predicate(
    observed: Any,
    predicate: dict[str, Any],
    expected_quantity: Quantity | None = None,
    policy: MeasurementPolicy | None = None,
) -> _Outcome:
    """Decide one subject, keeping units attached to both sides of the comparison.

    Values that are not measurements — booleans, labels — are compared directly.
    Measurements are normalized into the unit the requirement is written in, and
    a comparison that would cross an unresolved or incompatible unit raises
    instead of producing a number.
    """
    operator = predicate.get("operator", "==")
    if operator not in OPERATORS:
        raise ValueError(f"unsupported predicate operator: {operator}")
    policy = policy or MeasurementPolicy()
    observed_quantity = Quantity.parse(observed)
    if observed_quantity is None or expected_quantity is None:
        return _Outcome(
            conforms=OPERATORS[operator](observed, predicate.get("value")),
            observed=observed,
            expected=f"{operator} {predicate.get('value')}",
        )
    assumption: dict[str, Any] | None = None
    if not observed_quantity.resolved and expected_quantity.resolved and policy.assumed_unit:
        # An assumption is only permitted because the obligation declared it, and
        # it is recorded so a reviewer sees the determination did not measure it.
        observed_quantity = Quantity(observed_quantity.value, policy.assumed_unit, provenance="assumed")
        assumption = {
            "kind": "unit_assumption",
            "property": predicate.get("property"),
            "assumedUnit": policy.assumed_unit,
            "basis": policy.assumption_basis or "declared by the obligation measurement policy",
        }
    conversion = normalize_for_comparison(observed_quantity, expected_quantity)
    return _Outcome(
        conforms=compare_values(
            conversion.normalized.value,
            operator,
            expected_quantity.value,
            relative_tolerance=policy.relative_tolerance,
        ),
        observed=observed_quantity.to_dict(),
        expected=f"{operator} {expected_quantity}",
        measurement=conversion.to_dict(),
        assumption=assumption,
    )


def validate_obligation(obligation: Obligation, vocabulary: Vocabulary | None = None) -> None:
    """Reject an obligation that cannot be evaluated as written.

    A predicate unit that measures something other than the vocabulary's
    declared dimension for that property is an authoring error. Reporting it as
    a finding about the project would blame the model for a mistake in the
    requirement.
    """
    vocabulary = vocabulary or Vocabulary.empty()
    declared = vocabulary.declared_dimension(obligation.predicate.get("property"))
    unit = resolve_unit(obligation.predicate.get("unit"))
    if declared is None or unit is None:
        return
    actual = dimension_of(unit).value
    if actual != declared:
        raise AssuranceError(
            f"predicate unit {unit!r} measures {actual}, but the vocabulary declares "
            f"{obligation.predicate.get('property')!r} as {declared}"
        )


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


def evaluate_obligation(obligation: Obligation, world: ProjectWorld, *, vocabulary: Vocabulary | None = None) -> Determination:
    """Evaluate one obligation against one snapshot.

    ``vocabulary`` is empty by default: the kernel resolves spellings but makes
    no domain claims. Adapters inject a pack.
    """
    vocabulary = vocabulary or Vocabulary.empty()
    validate_obligation(obligation, vocabulary)
    spec = PopulationSpec.from_dict(obligation.population)
    population = [element for element in world.elements if _matches_population(element, spec, vocabulary)]
    if not population:
        return _empty_population_determination(obligation, spec)

    property_name = obligation.predicate.get("property")
    policy = MeasurementPolicy.from_dict(obligation.measurement)
    expected_quantity = Quantity.parse(obligation.predicate.get("value"), obligation.predicate.get("unit"))
    evaluated = 0
    conforming = 0
    evidence_ids: list[str] = []
    unknowns: list[Unresolved] = []
    reasons: list[str] = []
    assumptions: list[Any] = list(spec.assumptions)
    counterexamples: list[Counterexample] = []

    for element in population:
        resolved = resolve_property(element, property_name, vocabulary)
        if resolved is None or resolved[1] is None:
            unknowns.append(Unresolved(
                element.element_id,
                DeterminationReason.MISSING_OBSERVATION.value,
                _evidence_for(element, property_name, resolved[0] if resolved else None),
                f"no value for property {property_name}",
            ))
            if DeterminationReason.MISSING_OBSERVATION.value not in reasons:
                reasons.append(DeterminationReason.MISSING_OBSERVATION.value)
            continue
        actual_property, observed = resolved
        element_evidence = _evidence_for(element, property_name, actual_property)
        try:
            outcome = _check_predicate(observed, obligation.predicate, expected_quantity, policy)
        except MeasurementError as error:
            # An unresolved or incompatible unit is not a violation. The subject
            # stays unevaluated rather than being decided numerically, and the
            # evidence that was inspected is recorded as inspected.
            unknowns.append(Unresolved(element.element_id, error.reason, element_evidence, str(error)))
            if error.reason not in reasons:
                reasons.append(error.reason)
            continue
        except (TypeError, ValueError) as error:
            unknowns.append(Unresolved(
                element.element_id,
                DeterminationReason.PREDICATE_NOT_EVALUABLE.value,
                element_evidence,
                str(error),
            ))
            if DeterminationReason.PREDICATE_NOT_EVALUABLE.value not in reasons:
                reasons.append(DeterminationReason.PREDICATE_NOT_EVALUABLE.value)
            continue
        # Evidence is cited only once the subject was actually evaluated, so a
        # determination never rests on evidence for a subject it could not decide.
        evaluated += 1
        evidence_ids.extend(element_evidence)
        if outcome.assumption is not None and outcome.assumption not in assumptions:
            assumptions.append(outcome.assumption)
        if outcome.conforms:
            conforming += 1
        else:
            counterexamples.append(
                Counterexample(
                    subject=element.element_id,
                    observed=outcome.observed,
                    expected=outcome.expected,
                    evidence_ids=element_evidence,
                    reason=f"property {property_name} does not satisfy predicate",
                    measurement=outcome.measurement,
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
        assumptions=tuple(assumptions),
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


def observe_measurement(value: Any, obligation: Obligation) -> dict[str, Any] | None:
    """The measurement audit for a raw observation, in the obligation's unit.

    Returns None when the value is not a measurement, or when the units cannot
    be reconciled — in which case the determination will have recorded the
    subject as unevaluated rather than compared it.
    """
    observed = Quantity.parse(value)
    if observed is None:
        return None
    expected = Quantity.parse(obligation.predicate.get("value"), obligation.predicate.get("unit"))
    if expected is None:
        return Conversion(observed, observed).to_dict()
    policy = MeasurementPolicy.from_dict(obligation.measurement)
    if not observed.resolved and expected.resolved and policy.assumed_unit:
        observed = Quantity(observed.value, policy.assumed_unit, provenance="assumed")
    try:
        return normalize_for_comparison(observed, expected).to_dict()
    except MeasurementError:
        return None
