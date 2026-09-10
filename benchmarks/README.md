# SFC Bench

Benchmarks will use synthetic fixtures and published ground truth. Metrics
include accuracy, coverage, evidence precision and recall, unsupported claims,
latency, tokens and cost. Customer requirements and real project files do not
belong here.

`sfc bench` currently scores status, evidence and counterexample precision and
recall, false closure rate and population coverage when the fixture supplies
truth. Provider metrics stay explicitly unscored without an agent trace.
