# IFC panel clearance

This fixture exercises the dependency-free STEP reader across a unit boundary.
The model is metric — `IFCUNITASSIGNMENT` declares metres, and each
`WorkingClearance` is an `IFCLENGTHMEASURE` — while the requirement is written
in inches. The reader attaches the project unit to the measurement, and the
kernel normalizes before comparing:

```
raw         0.74676 m     (source: IFCUNITASSIGNMENT)
normalized  29.4 in
requirement >= 36 in
            -> NOT_MET
```

The full conversion is recorded on the counterexample and on the admitted
evidence, so a reviewer can check how the compared number was produced. Had the
connector ignored the unit assignment, `0.74676 >= 36` would still have read as
a failure — but `740 mm >= 36` would have read as compliance. See ADR 0008.

```bash
python -m sfc ifc-import examples/ifc-panel-clearance/demo.ifc --output .sfc/ifc-world.json
python -m sfc verify examples/ifc-panel-clearance/requirement.json .sfc/ifc-world.json
```

The reader is conservative: unsupported IFC entities are ignored rather than
invented, and a unit assignment SFC cannot express is reported in
`metadata.unresolvedUnitTypes` rather than guessed. `IFCREAL` and `IFCINTEGER`
values stay dimensionless, because the source declared no unit. For production
IFC coverage, an adapter can replace the reader while returning the same
Project World contract.

