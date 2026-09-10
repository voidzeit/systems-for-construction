# SFC Bench

A benchmark fixture contains a requirement, Project World and optional truth.
The runner executes the real deterministic assurance path. With truth it scores
status accuracy, evidence precision and recall, counterexample precision and
recall, false closure rate and expected population coverage. Without truth it
emits `not_scored_without_fixture_truth`; it never fabricates a score.

Provider-dependent metrics such as tokens, cost and unsupported agent claims
remain explicitly unscored until a provider trace is included in the fixture.
