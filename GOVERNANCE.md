# Governance

SFC is maintained in the open. Technical decisions are documented in ADRs and substantial changes should explain the affected contract, authority boundary and migration path. Maintainers protect the provider-neutral core and the evidence and provenance guarantees.

The project is alpha software. A release may change APIs until a later stability declaration, but changes to canonical run semantics, evidence authority or publication guarantees require an ADR.

## Knowledge exposure

SFC uses an explicit knowledge-exposure classification, **SFC-K0 through SFC-K7**, to separate critical secrets and private production intelligence from customer, partner, open-source and public-market knowledge.

The public `systems-for-construction` repository is a **K5–K7 surface**. It may contain open contracts, protocols, schemas, SDKs, reference behavior, interoperability, public research and market-facing material. K0–K4 artifacts must remain in appropriately controlled systems.

See [SFC Knowledge Exposure Policy](docs/governance/knowledge-exposure-policy.md) for the canonical classification, disclosure review and repository-boundary rules.
