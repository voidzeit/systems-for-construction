# Work Units

A Work Unit is the smallest governed unit of SFC production.

\[
Project \rightarrow Scope \rightarrow WorkPackage \rightarrow WorkUnit
\]

It records the package, required capability, inputs, dependencies, executor, expected output, acceptance/QA criteria, evidence and lifecycle state. It deliberately does not prescribe private routing or optimization logic.

Canonical lifecycle:

~~~text
CREATED → READY → RUNNING
                   ├ BLOCKED → READY
                   ├ RETRY → RUNNING
                   └ CANCELLED
RUNNING → MACHINE_QA → HUMAN_REVIEW
                       ├ CORRECTION → READY
                       ├ ESCALATED
                       └ ACCEPTED → DELIVERED → LEARNED
~~~

The invariant is **orchestrate work, not agents**. Humans, deterministic code, AEC runtimes, models, solvers and hybrid workflows are replaceable executors.
