"""Semantic conformance for SFC documents, at the level JSON Schema cannot reach.

A contract needs two layers, and they answer different questions:

    JSON Schema             shape, types, required fields, enums
    semantic conformance    invariants that relate one field to another

``spec/*.schema.json`` covers the first. It cannot express that the evidence a
determination rests on must be disjoint from the evidence merely inspected, or
that a proof must describe the determination it travels with, because those are
statements about several fields at once and about agreement between documents.

Without this layer the guarantee would be "the Python producer is correct"
rather than "the contract cannot be violated". Any producer - a connector, a
service in another language, a third-party agent - can write JSON directly, so
the invariants have to live at the boundary, not inside one implementation.

The rules are checked against plain dictionaries rather than SFC classes, so a
document that never passed through this runtime can still be examined:

    validate_schema(document)      # jsonschema, a development dependency
    validate_semantics(document)   # here, stdlib only

Every violation is collected before raising, because a producer fixing a
document wants the whole list, not the first line of it.
"""

from __future__ import annotations

from typing import Any, Iterable

#: Coverage is published rounded, so it is compared at that precision.
COVERAGE_TOLERANCE = 1e-6

CLOSING_RESULTS = frozenset({"MET", "NOT_MET", "NOT_APPLICABLE"})


class ConformanceError(ValueError):
    """Raised when a document is well-formed but semantically impossible."""

    def __init__(self, kind: str, violations: tuple[str, ...]) -> None:
        self.kind = kind
        self.violations = violations
        detail = "\n".join(f"  - {violation}" for violation in violations)
        super().__init__(f"{kind} violates {len(violations)} SFC invariant(s):\n{detail}")


def validate_semantics(kind: str, document: dict[str, Any]) -> None:
    """Check one document against the cross-field invariants for its kind.

    ``kind`` is the schema filename the document claims to satisfy, so a caller
    that already dispatches on schema name needs no second vocabulary.
    """
    checks = {
        "determination.schema.json": determination_violations,
        "proof.schema.json": proof_violations,
        "run.schema.json": run_violations,
    }
    if kind not in checks:
        raise ValueError(f"no semantic rules are defined for {kind!r}")
    violations = tuple(checks[kind](document))
    if violations:
        raise ConformanceError(kind, violations)


def determination_violations(document: dict[str, Any]) -> Iterable[str]:
    """Invariants a determination must satisfy whoever produced it."""
    population = document.get("population") or {}
    expected = population.get("expected")
    evaluated = population.get("evaluated")
    coverage = document.get("coverage")
    quantifier = document.get("quantifier")
    status = document.get("determination")
    supporting = _ids(document.get("evidenceIds"))
    inspected = _ids(document.get("inspectedEvidenceIds"))
    witnesses = _ids(document.get("witnesses"))
    failing = tuple(str(item.get("subject", "")) for item in document.get("counterexamples") or ())
    undecided = tuple(str(item.get("subject", "")) for item in document.get("unknowns") or ())

    yield from _population_violations(expected, evaluated, document.get("conforming"), coverage)
    yield from _evidence_violations(supporting, inspected, document.get("unknowns") or ())
    yield from _subject_violations(witnesses, failing, undecided, document.get("conforming"))

    if status == "MET":
        if expected == 0:
            yield "MET over an empty population: absence is not compliance"
        elif quantifier == "ANY":
            if not witnesses:
                yield "ANY/MET names no witness, so nothing establishes the claim"
        else:
            if expected != evaluated:
                yield f"{quantifier}/MET leaves {_undecided_count(expected, evaluated)} subject(s) unevaluated"
            if undecided:
                yield f"{quantifier}/MET leaves subject(s) undecided: {sorted(set(undecided))}"
            if quantifier == "ALL" and failing:
                yield f"ALL/MET carries counterexample(s): {sorted(set(failing))}"
            if quantifier == "NONE" and witnesses:
                yield f"NONE/MET names subject(s) that satisfy the predicate: {sorted(set(witnesses))}"
    if status == "NOT_MET":
        if quantifier == "ALL" and not failing:
            yield "ALL/NOT_MET carries no counterexample, so nothing establishes the violation"
        if quantifier == "NONE" and not witnesses:
            yield "NONE/NOT_MET names no subject that satisfies the predicate"
        if quantifier == "ANY" and expected != evaluated:
            yield "ANY/NOT_MET before the whole population was evaluated"
    if status == "NOT_APPLICABLE":
        if expected:
            yield f"NOT_APPLICABLE over a population of {expected}"
        if not supporting:
            yield "NOT_APPLICABLE without evidence that the requirement does not apply"


def proof_violations(document: dict[str, Any]) -> Iterable[str]:
    """A proof carries the same population and evidence rules as its result."""
    population = document.get("population") or {}
    yield from _population_violations(
        population.get("expected"),
        population.get("evaluated"),
        None,
        document.get("coverage"),
    )
    yield from _evidence_violations(
        _ids(document.get("evidence")),
        _ids(document.get("inspectedEvidence")),
        document.get("unknowns") or (),
    )
    if document.get("result") in CLOSING_RESULTS and document.get("result") != "NOT_APPLICABLE":
        if not document.get("claims"):
            yield f"{document.get('result')} proof states no claim"


#: Fields a run's proof must repeat from the determination it travels with. A
#: proof that disagrees describes some other evaluation.
_PROOF_TO_DETERMINATION = (
    ("requirementId", "requirementId"),
    ("population", "population"),
    ("coverage", "coverage"),
    ("result", "determination"),
    ("evidence", "evidenceIds"),
    ("inspectedEvidence", "inspectedEvidenceIds"),
    ("witnesses", "witnesses"),
)


def run_violations(document: dict[str, Any]) -> Iterable[str]:
    """A run is its determination, plus a proof that must describe it."""
    determination = document.get("determination")
    if not isinstance(determination, dict):
        yield "run carries no determination"
        return
    for violation in determination_violations(determination):
        yield f"determination: {violation}"

    proof = document.get("proof")
    if proof is None:
        return
    if not isinstance(proof, dict):
        yield "proof is present but is not an object"
        return
    for violation in proof_violations(proof):
        yield f"proof: {violation}"
    for proof_field, determination_field in _PROOF_TO_DETERMINATION:
        if proof_field not in proof:
            continue
        stated = proof[proof_field]
        actual = determination.get(determination_field)
        if _normalize(stated) != _normalize(actual):
            yield (
                f"proof {proof_field} does not describe this determination: "
                f"{stated!r} against {actual!r}"
            )


def _population_violations(
    expected: Any,
    evaluated: Any,
    conforming: Any,
    coverage: Any,
) -> Iterable[str]:
    if not isinstance(expected, int) or not isinstance(evaluated, int):
        yield "population must state an integer expected and evaluated count"
        return
    if evaluated > expected:
        yield f"evaluated {evaluated} exceeds expected {expected}"
    if isinstance(conforming, int) and conforming > evaluated:
        yield f"conforming {conforming} exceeds evaluated {evaluated}"
    if coverage is None:
        if expected:
            yield f"coverage is absent over a population of {expected}"
        return
    if not expected:
        yield f"coverage {coverage} over an empty population: a fraction of nothing"
        return
    if not 0 <= coverage <= 1:
        yield f"coverage {coverage} is outside [0, 1]"
        return
    if abs(coverage - evaluated / expected) > COVERAGE_TOLERANCE:
        yield f"coverage {coverage} does not describe {evaluated} of {expected} subjects"


def _evidence_violations(
    supporting: tuple[str, ...],
    inspected: tuple[str, ...],
    unknowns: Iterable[dict[str, Any]],
) -> Iterable[str]:
    """Supporting and inspected evidence are different claims about evidence.

    Supporting evidence is what the determination rests on. Inspected evidence
    is what the investigation looked at on subjects it could not decide. A
    document listing an identifier as both asserts that the conclusion rests on
    evidence for a subject it never decided.
    """
    overlap = sorted(set(supporting) & set(inspected))
    if overlap:
        yield f"evidence is both supporting and merely inspected: {overlap}"
    for name, ids in (("evidenceIds", supporting), ("inspectedEvidenceIds", inspected)):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            yield f"{name} repeats: {duplicates}"
    examined = {
        str(evidence_id)
        for item in unknowns
        for evidence_id in item.get("evidenceIds") or ()
    }
    unaccounted = sorted(examined - set(supporting) - set(inspected))
    if unaccounted:
        yield f"evidence examined on an undecided subject is listed nowhere: {unaccounted}"
    invented = sorted(set(inspected) - examined)
    if invented:
        yield f"inspected evidence belongs to no undecided subject: {invented}"


def _subject_violations(
    witnesses: tuple[str, ...],
    failing: tuple[str, ...],
    undecided: tuple[str, ...],
    conforming: Any,
) -> Iterable[str]:
    if isinstance(conforming, int) and len(witnesses) > conforming:
        yield f"{len(witnesses)} witnesses exceed {conforming} conforming subject(s)"
    for first, second, message in (
        (witnesses, failing, "both satisfies and fails the predicate"),
        (witnesses, undecided, "is both a witness and undecided"),
        (failing, undecided, "is both a counterexample and undecided"),
    ):
        overlap = sorted(set(first) & set(second))
        if overlap:
            yield f"subject(s) {overlap}: {message}"


def _ids(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in value or ())


def _normalize(value: Any) -> Any:
    """Compare list-valued fields by content, so tuple and list agree."""
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in sorted(value.items())}
    return value


def _undecided_count(expected: Any, evaluated: Any) -> int:
    return expected - evaluated if isinstance(expected, int) and isinstance(evaluated, int) else 0
