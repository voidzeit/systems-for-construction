# ADR 0012 — Plugin manifests declare capability and side effects

**Status:** Accepted

An extension cannot be trusted merely because it is installed. Every SFC-compatible plugin declares capabilities, permissions, side effects and an autonomy ceiling.

A plugin cannot self-grant authority. Side-effecting execution remains subject to runtime policy, evidence and acceptance.

The manifest is an open interface; implementation intelligence may remain private.
