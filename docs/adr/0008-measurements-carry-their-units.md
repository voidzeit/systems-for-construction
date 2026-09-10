# ADR 0008: A measurement carries its unit, and an unresolved unit is never compared

## Status

Accepted.

## Context

The first implementation compared bare numbers. Three gaps compounded into one
failure mode:

1. The requirement compiler captured the unit in its regex and discarded it.
   `"36 inches"` and `"36 mm"` compiled to the identical predicate
   `{property: working_clearance_inches, operator: ">=", value: 36}`.
2. The IFC connector ignored `IFCUNITASSIGNMENT` entirely. An
   `IFCLENGTHMEASURE` is expressed in project units — commonly metres — and was
   read as a dimensionless number.
3. Property-name normalization stripped an `inches` suffix, so the IFC property
   `WorkingClearance` matched the obligation property
   `working_clearance_inches` and was compared numerically against 36.

The result was a determination that compared `0.74676` against `36` and reported
`NOT_MET` — the right verdict reached for the wrong reason, and only by
coincidence. Had the model been in millimetres, `740` would have compared as
`>= 36` and reported `MET` on a clearance of 74 cm against a 91 cm requirement.

The determination's `assumptions` field was empty throughout. Nothing recorded
that a unit had been assumed. For a system whose thesis is evidence with
provenance, a correct number with the wrong unit was indistinguishable from a
valid result.

## Decision

A measurement is a domain object. Value, unit and dimension travel together
through parsing, conversion and comparison.

```
Quantity(value=0.74676, unit="m", dimension=length)
```

Both sides of a predicate are quantities:

```
expected:  36 in          (predicate value + predicate unit)
observed:  0.74676 m      (property value + connector-resolved unit)

normalize to the requirement's unit
        |
expected:  36 in
observed:  29.4 in
        |
29.4 < 36  ->  NOT_MET
```

Four rules govern comparison:

| Observed | Expected | Result |
| --- | --- | --- |
| unit known | unit known, same dimension | normalized, then compared |
| unit known | unit known, different dimension | `INCOMPLETE`, `INCOMPATIBLE_MEASUREMENT_DIMENSION` |
| unit absent | unit known | `INCOMPLETE`, `UNRESOLVED_MEASUREMENT_UNIT` |
| unit absent | unit absent | compared as declared dimensionless values |

A subject whose unit cannot be resolved is recorded as unevaluated. It does not
become a counterexample, it does not lower `conforming`, and it does not
contribute evidence — an unresolved unit is a gap in the measurement model, not
a violation. This is `ADR 0003` applied to units.

An unrecognized unit token raises rather than degrading to dimensionless. The
requirement compiler surfaces that as a compilation error, because a controlled
language should refuse an input it cannot represent instead of guessing.

### Units are read from the source, not inferred

The IFC connector resolves `IFCUNITASSIGNMENT` into a canonical unit per unit
type, and attaches it to typed measures only:

```
IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)         -> length = m
IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)   -> length = mm
IFCCONVERSIONBASEDUNIT(...,.LENGTHUNIT.,'inch',...) -> length = in

IFCPROPERTYSINGLEVALUE('WorkingClearance',$,IFCLENGTHMEASURE(0.74676),$)
        |
{"value": 0.74676, "unit": "m", "ifcType": "IFCLENGTHMEASURE",
 "provenance": "IFCUNITASSIGNMENT"}
```

`IFCREAL`, `IFCINTEGER` and `IFCNUMBER` stay dimensionless: the source declared
no unit, so neither does SFC. A unit assignment SFC cannot express is reported
in `metadata.unresolvedUnitTypes` and leaves the measurement unresolved.

### A resolved unit is evidence; an assumed unit is an assumption

These are different claims and are recorded differently.

- The project declares metres and the property is an `IFCLENGTHMEASURE`. The
  unit is *derived from the source*, and the conversion audit records
  `source: "IFCUNITASSIGNMENT"`.
- A property name suggests inches but the source declares nothing. That is an
  assumption. It is permitted only when the obligation declares it:

```json
"measurement": {
  "assumeObservedUnit": "in",
  "assumptionBasis": "legacy vocabulary mapping"
}
```

and it is then recorded on the determination:

```json
{"kind": "unit_assumption", "property": "working_clearance",
 "assumedUnit": "in", "basis": "legacy vocabulary mapping"}
```

Without that declaration the subject stays unevaluated. Policy grants the
assumption; the determination discloses it. `Evidence -> Policy -> Determination`.

### Every normalization is auditable

Evidence and counterexamples carry the full trail, so a reviewer can reconstruct
exactly how the compared number was produced:

```json
{"rawValue": 0.74676, "rawUnit": "m",
 "normalizedValue": 29.4, "normalizedUnit": "in",
 "dimension": "length", "conversion": 39.37007874015748,
 "source": "IFCUNITASSIGNMENT"}
```

### Converted measurements compare with a tolerance

Unit conversion is not exact in binary floating point: 12 in is exactly
0.3048 m, but converting 0.3048 m to inches yields 12.000000000000002. A strict
comparison would report a violation that does not exist. Converted measurements
are compared with a relative tolerance, `1e-9` by default and adjustable through
`measurement.relativeTolerance`. Values that are not measurements keep exact
comparison.

## Consequences

- `working_clearance_inches` is an antipattern and is gone from the examples.
  The unit belongs to the value, not to the property name, and the name-based
  `inches` suffix stripping is removed from property resolution. Case and
  punctuation normalization stays: `WorkingClearance` resolving
  `working_clearance` is syntax, not a claim about the measurement.
- `spec/obligation.schema.json` gains `predicate.unit` and an obligation-level
  `measurement` policy. `spec/evidence.schema.json` and the determination's
  counterexamples gain the `measurement` audit. `assumptions` holds structured
  records rather than free text.
- Project World property values may be a scalar or a `{value, unit}` mapping.
  Scalars keep working and are treated as declaring no unit, which is what they
  are.
- The IFC fixture is now a realistic metric file, and the requirement written
  against it is imperial. The example exercises a real cross-unit comparison
  instead of a coincidence.

## Alternatives considered

**Normalize everything to SI at the boundary.** Rejected: the determination
should be legible in the unit the requirement is written in, and discarding the
raw value would destroy the audit trail that makes the conversion checkable.

**Treat a missing unit as the requirement's unit.** Rejected: that is exactly
the silent assumption this ADR exists to remove. It is available, but only when
an obligation declares it and the determination records it.

**Depend on `pint` or a similar units library.** Rejected: SFC Core is
stdlib-only by `ADR 0001`. The registry SFC needs is a table of construction
units, small enough to read in one screen and to audit.
