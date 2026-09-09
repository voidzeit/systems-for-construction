# Electrical panel clearance

This synthetic fixture demonstrates the smallest complete SFC flow:

- population: 18 electrical panels;
- quantifier: `ALL`;
- predicate: `working_clearance_inches >= 36`;
- result: 17 conforming panels and one counterexample (`LP-18`, 29.4 inches).

Run it from the repository root after installing the package:

```bash
python -m sfc verify examples/electrical-panel-clearance/requirement.json examples/electrical-panel-clearance/project-world.json
```

The data is synthetic and contains no customer project information.

