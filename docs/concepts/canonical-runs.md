# Canonical runs

A run freezes its Project World and obligation hashes before evaluation. The
result is written to a run directory and then the canonical pointer is replaced
atomically. If evaluation or serialization fails, the previous canonical run
remains intact.

This filesystem implementation is a reference adapter. A database or durable
workflow service can implement the same lifecycle: freeze, plan, execute,
checkpoint, validate and publish.

