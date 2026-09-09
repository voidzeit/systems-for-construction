# Evidence and authority

SFC keeps three ideas separate:

1. A source observation is evidence-shaped data.
2. A candidate claim is a proposal from a connector or agent.
3. Admitted evidence has sufficient source authority, provenance and valid confidence.

`EvidenceAuthority` is the admission boundary. An agent self-report can be
stored as a candidate with authority `0.5`, but the default policy does not
admit it as official evidence. Missing evidence produces `INCOMPLETE` or
`UNKNOWN`; it never becomes `NOT_MET` by implication.

