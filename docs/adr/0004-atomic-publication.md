# ADR 0004: Publish canonical runs atomically

Status: accepted

Each completed run is durable before the canonical pointer changes. A failed
run must never replace the last valid published run.

