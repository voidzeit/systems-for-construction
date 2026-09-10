# SFC vocabulary

Two different things live here.

`statuses.md` is the status vocabulary: the state names and transitions SFC
itself defines.

Vocabulary **packs** are something else: declared discipline terms that the
assurance kernel deliberately does not contain. `../vocabulary.schema.json` is
their portable contract, and `packages/sfc-core/src/sfc/vocabularies/` holds the
packs that ship with the reference implementation.

## Why packs exist

The kernel knows `Population`, `Predicate`, `Observation`, `Quantity` and
`Evidence`. It does not know what an electrical panel is. Left in the kernel,
domain terms accumulate into a chain of discipline branches, which is the
opposite of a provider-neutral core:

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

## Format

```json
{
  "vocabularyId": "sfc.vocabulary.aec-core",
  "version": "1",
  "kinds": [
    {
      "canonical": "electrical_distribution_board",
      "aliases": ["electrical_panel", "distribution_board", "IfcElectricDistributionBoard"]
    }
  ],
  "properties": [
    {
      "canonical": "working_clearance",
      "dimension": "length",
      "aliases": ["WorkingClearance", "working_clearance_inches"]
    }
  ]
}
```

`canonical` is the term a determination is written against. `aliases` are the
spellings a connector, a schedule or a requirement author may produce for it.
Lookup is normalization-insensitive, so an alias only needs to be listed once
per spelling that differs by more than punctuation and case.

`dimension` declares what a property measures. It lets SFC reject an obligation
whose predicate unit measures something else — a `working_clearance >= 500 kg`
predicate is an authoring error, and reporting it as a finding about the project
would blame the model for a mistake in the requirement.

## Using a pack

The kernel takes no pack by default and makes no domain claims:

```python
evaluate_obligation(obligation, world)                      # spelling only
evaluate_obligation(obligation, world, vocabulary=pack)     # declared terms
```

Adapters inject one. The CLI uses the bundled pack unless told otherwise:

```bash
sfc vocabulary                          # show the pack a determination would use
sfc verify req.json world.json          # bundled pack
sfc verify req.json world.json --vocabulary ./packs/electrical.json
sfc verify req.json world.json --no-vocabulary
```

`SFC_VOCABULARY_PATH` replaces the bundled pack with a file or a directory, so a
project can supply its own discipline terms without a code change. A directory
loads every `*.json` in it as one merged pack, with earlier terms winning.

## Adding a term

Adding an alias is a claim that two names denote the same thing. It belongs in a
pack rather than in code precisely so that a reviewer can read every such claim
a determination depends on, and so a project can disagree with one.
