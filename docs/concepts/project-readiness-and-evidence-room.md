# Project readiness and Evidence Room

SFC treats a document as a versioned source and evidence as a governed claim
derived from that source. `EvidenceRoom` keeps document content hashes,
version identity and evidence lifecycle state while `EventLog` preserves the
history of transitions.

`compute_readiness` produces a transparent operational index from supplied
determinations and evidence. It reports requirements covered, population
evaluated, evidence grounding, explicitly reported freshness, unresolved
contradictions and unknown rate. Missing metrics remain unavailable instead of
being converted to zero. Contributions identify which requirement or evidence
resource affected the index; the index is a readiness signal, never an
engineering determination.

`RealityObservation` is the first physical-world contract. It can be admitted
as `point_cloud_segment` evidence when provenance is present, and
`compare_position` returns `UNKNOWN` when either expected or observed geometry
is missing. A point-cloud parser and geometry engine remain separate adapters.
