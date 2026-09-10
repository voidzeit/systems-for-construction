# Evidence and authority

SFC keeps three ideas separate:

1. A source observation is evidence-shaped data.
2. A candidate claim is a proposal from a connector or agent.
3. Admitted evidence has sufficient source authority, provenance and valid confidence.

`EvidenceAuthority` is the admission boundary. An agent self-report can be
stored as a candidate with authority `0.5`, but the default policy does not
admit it as official evidence. Missing evidence produces `INCOMPLETE` or
`UNKNOWN`; it never becomes `NOT_MET` by implication.

## Supporting evidence and inspected evidence

A determination keeps two evidence lists, because they make different claims.

```
Population            B-1  B-2  B-3  B-4  B-5
Evidence on record    E-1  E-2  E-3  E-4  E-5

evidenceIds           E-1  E-2          supports the determination
inspectedEvidenceIds            E-3  E-4  E-5   looked at, decided nothing
```

`evidenceIds` is the evidence the conclusion rests on. Only subjects that were
actually evaluated contribute to it. `inspectedEvidenceIds` is what was examined
on subjects the determination could not decide.

Each unresolved subject records why, with a machine-readable reason and the
evidence it was examined with:

```json
{"subject": "B-3", "reason": "UNRESOLVED_MEASUREMENT_UNIT",
 "evidenceIds": ["E-3"],
 "detail": "cannot compare 29.4 against 36 in: the observation declares no unit"}
```

Citing E-3 as supporting evidence would assert that the determination rests on
an observation it never compared. Dropping it would hide that the observation
exists and was looked at. Both lists are needed, and a proof reports both.
