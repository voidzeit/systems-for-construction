# ADR 0011 — Work Unit is the durable production primitive

**Status:** Accepted

SFC orchestrates work, not agents. The portable Work Unit identifies required capability, dependencies, inputs, acceptance and evidence independently of who or what executes it.

Executors are replaceable; the work contract is durable.

The public contract contains lifecycle semantics and interoperable fields. Private routing, ranking and accumulated production intelligence are not part of this ADR.
