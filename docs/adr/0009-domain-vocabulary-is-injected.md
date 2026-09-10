# ADR 0009: Domain vocabulary is injected, not built into the kernel

## Status

Accepted.

## Context

The assurance kernel contained a hardcoded alias table:

```python
aliases = {
    "electrical_panel": {"electrical_panel", "electricdistributionboard", ...},
    ...
}
```

and the requirement compiler contained a second one, mapping subject phrases and
property names to the same handful of electrical terms. The first demo case had
been written into the generic evaluation engine.

That does not scale, and it fails in a specific direction. Adding air handling
units, fire dampers, structural columns, emergency exits, door clearances and
pipe slopes turns the kernel into a chain of discipline branches:

```
if electrical...
elif mechanical...
elif plumbing...
elif structural...
```

The deeper problem is not size. An alias is a *claim* — that two names denote
the same equipment or the same measurement. Claims of that kind belong where a
reviewer can read them and a project can disagree with them. Buried in the
kernel, every determination silently depended on assertions nobody could audit
without reading Python.

## Decision

The kernel holds no domain vocabulary. It knows `Population`, `Predicate`,
`Observation`, `Quantity` and `Evidence`, and nothing about construction.

```
SFC Kernel
     |
     | consumes
     v
Vocabulary pack
     |
     +-- core
     +-- IFC
     +-- electrical
     +-- mechanical
     +-- customer or discipline pack
```

Terms live in declared packs with a portable schema,
`spec/vocabulary.schema.json`:

```json
{
  "canonical": "electrical_distribution_board",
  "aliases": ["electrical_panel", "distribution_board", "IfcElectricDistributionBoard"]
}
```

`evaluate_obligation` takes an optional `vocabulary`. **The default is empty.**
The kernel still normalizes punctuation and case, because a name written in
camel case and the same name written in snake case are one name written two
ways — that is spelling, not a domain assertion. It will not claim that
`electrical_panel` and `electricdistributionboard` are the same equipment.

Adapters inject a pack: the CLI, the investigation path and the benchmark runner
all pass one. `SFC_VOCABULARY_PATH` or `--vocabulary` replaces it, and
`--no-vocabulary` runs the bare kernel.

### The default composes with ADR 0007

Without a pack, a requirement written against `electrical_panel` and a model
containing `electricdistributionboard` produce an empty population. Under
ADR 0007 that is `INCOMPLETE` with reason `EMPTY_POPULATION_UNRESOLVED` — never
`MET`. The two decisions together mean an unrecognized term degrades into a
visible gap rather than a false closure:

```
sfc verify ... --no-vocabulary   ->  INCOMPLETE  (EMPTY_POPULATION_UNRESOLVED)
sfc verify ...                   ->  NOT_MET     (evaluated against the pack)
```

### Declared dimensions catch authoring errors

A property term may declare what it measures. `working_clearance` is a length,
so an obligation whose predicate reads `>= 500 kg` is rejected as an authoring
error rather than evaluated. Reporting it as a finding would blame the model for
a mistake in the requirement.

## Consequences

- `tests/test_vocabulary.py` asserts that the kernel source names no discipline
  terms at all. The guard is deliberately blunt: a term reappearing in the
  kernel, even in a comment, fails the build.
- The requirement compiler keeps grammar — plural handling — and delegates every
  domain mapping to the pack. Its docstring now says what it is: a compiler for
  a *controlled* requirement language, not a general natural-language compiler.
- `resolve_property` and `compile_requirement` gain an optional vocabulary
  argument, defaulting to empty, so existing callers keep working with kernel
  semantics.
- `sfc vocabulary` prints the pack a determination would use, so the terms in
  play are inspectable before a run rather than inferred after one.
- The bundled pack ships as package data and is validated against its schema by
  the conformance gate, so a malformed or drifting pack fails CI.

## Alternatives considered

**Keep the aliases but move them to a module-level constant.** Rejected: it
would still be code, still unreadable to a reviewer, and still unmodifiable by a
project without a fork.

**Default to the bundled pack inside the kernel.** Rejected: the kernel's
purity is the property worth protecting. A pack reaching it by default would
make the boundary a convention rather than a structure, and the first
convenience exception would erase it.

**Infer aliases from string similarity.** Rejected for the same reason
ADR 0008 rejects inferred units. A guess about what two names mean is not
evidence, and a determination should not rest on one.
