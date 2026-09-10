# Electrical panel clearance

This synthetic fixture demonstrates the smallest complete SFC flow:

- population: 18 electrical panels, `minimumExpected: 1`;
- quantifier: `ALL`;
- predicate: `working_clearance >= 36 in`;
- result: 17 conforming panels and one counterexample (`LP-18`, 29.4 in).

The unit lives on the measurement, not in the property name. Each observation is
a `{value, unit, provenance}` mapping, and the requirement declares the unit it
is written in, so the comparison is between two measurements rather than two
numbers. See ADR 0008.

`minimumExpected: 1` states that the requirement presupposes at least one panel.
Point the same requirement at a world with no panels and the determination is
`INCOMPLETE` with reason `EMPTY_POPULATION_UNRESOLVED`, never `MET`. See ADR 0007.

Run it from the repository root after installing the package:

```bash
python -m sfc verify examples/electrical-panel-clearance/requirement.json examples/electrical-panel-clearance/project-world.json
```

The data is synthetic and contains no customer project information.

The fixture also serves as the first `sfc bench` input. When no truth file is
present, benchmark metrics remain `not_scored_without_fixture_truth`.
