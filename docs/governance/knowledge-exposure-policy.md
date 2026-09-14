# SFC Knowledge Exposure Policy

**Status:** Canonical governance policy  
**Classification:** SFC-K5 — Open Technical Knowledge  
**Owner:** SFC Governance / Product Architecture  
**Scope:** All SFC code, documentation, research, datasets, models, product artifacts, customer artifacts, internal operating material and public communications.

## 1. Purpose

SFC deliberately separates what the market should be able to adopt from what must remain an accumulating competitive advantage.

The governing principle is:

> **Open contract. Private advantage.**

SFC publishes enough knowledge to create trust, interoperability, developer adoption and an open ecosystem, while protecting production intelligence, accumulated data, specialized models and other capabilities whose disclosure would materially reduce SFC's future ability to capture value.

Disclosure is often irreversible. A knowledge asset may move to a higher-exposure level only through deliberate review; publishing an asset does not restore secrecy if it is later reclassified downward.

## 2. Classification scale

SFC uses eight exposure classes, **SFC-K0** through **SFC-K7**.

Lower numbers mean lower exposure and higher strategic sensitivity.

```text
SFC-K7  Market Narrative
SFC-K6  Public Technical Knowledge
SFC-K5  Open Technical Knowledge / Open Source
SFC-K4  Partner / Developer
SFC-K3  Customer Confidential
SFC-K2  Company Internal
SFC-K1  Internal Restricted
SFC-K0  Critical Secret / Crown Jewels
```

The public `systems-for-construction` repository may contain only material approved for **SFC-K5 through SFC-K7**. K0–K4 artifacts belong in appropriately controlled systems and repositories.

---

## 3. SFC-K0 — Critical Secret / Crown Jewels

**Disclosure:** Prohibited outside specifically authorized SFC personnel and systems.  
**Access:** Strict need-to-know.

Examples include:

- proprietary datasets;
- customer-specific learning;
- accepted/rejected production corpora;
- learned constructability heuristics;
- production optimization methods;
- internal scoring and ranking;
- proprietary model weights;
- customer mappings;
- pricing and margin intelligence;
- private evaluation corpora;
- sensitive failure taxonomies;
- cross-customer learned patterns;
- security secrets, credentials and sensitive configuration.

These assets should generally be treated as trade secrets unless another protection mechanism is deliberately selected.

---

## 4. SFC-K1 — Internal Restricted

**Disclosure:** Restricted to designated SFC teams.  
**External publication:** Prohibited unless reclassified.

Typical examples:

- Production Intelligence internals;
- advanced requirement compilation;
- Production Planner internals;
- Generative MEP algorithms;
- Constructability Engine internals;
- advanced evidence ranking;
- model-routing policies;
- private evaluations;
- commercial domain packs;
- optimization logic;
- non-public orchestration algorithms.

This layer is expected to contain much of SFC's private technical advantage.

---

## 5. SFC-K2 — Company Internal

**Disclosure:** SFC personnel with a legitimate operational need.  
**External publication:** Not by default.

Examples:

- internal system architecture;
- production methodology;
- operating standards;
- internal QA procedures;
- internal KPIs;
- roadmaps;
- deployment practices;
- internal system diagrams;
- incident learnings;
- operating playbooks.

K2 material is not necessarily a crown jewel, but it exists to operate the company rather than to build the public ecosystem.

---

## 6. SFC-K3 — Customer Confidential

**Disclosure:** Authorized SFC personnel and the relevant customer under the applicable contractual and security boundary.

Examples:

- customer project state;
- project evidence;
- QA results;
- audit information;
- project metrics;
- customer-specific integrations;
- customer configuration;
- workflow state;
- security information appropriate for customer assurance.

A customer should be able to understand and trust the result without receiving SFC's private intelligence, cross-customer data, training details or internal heuristics.

---

## 7. SFC-K4 — Partner / Developer

**Disclosure:** Approved partners, integrators and developers under the applicable access terms.

Examples:

- non-public API contracts;
- partner SDK surfaces;
- schemas needed for an integration;
- events;
- connector interfaces;
- authentication patterns;
- sample integrations;
- extension points;
- integration test fixtures.

The principle is:

> **Expose what SFC expects, what SFC returns and how to integrate — not how private SFC intelligence reaches its answer.**

K4 may later be promoted to K5 when broad public adoption is strategically beneficial.

---

## 8. SFC-K5 — Open Technical Knowledge / Open Source

**Disclosure:** Public.  
**Typical license:** Apache-2.0 for source code unless another license is explicitly approved.

Examples may include:

- Project World contracts and schemas;
- Work Unit representations;
- requirement representation;
- evidence protocol;
- canonical run contracts;
- conformance rules;
- connector SDK;
- basic CLI;
- reference connectors;
- reference runtime;
- interoperability tooling;
- architecture principles;
- ADRs;
- small public reference projects;
- basic public benchmarks.

The primary test for K5 is:

> **Does SFC benefit if other tools and organizations adopt this abstraction, protocol or contract?**

If yes, the asset is a candidate for deliberate publication.

Reference behavior may be open even when the highest-performing production implementation remains private.

---

## 9. SFC-K6 — Public Technical Knowledge

**Disclosure:** Public.

This layer communicates methods, research and technical reasoning without necessarily publishing product implementation.

Examples:

- technical papers;
- engineering-AI research;
- benchmark methodology and selected results;
- failure analyses suitable for publication;
- AEC production methodology;
- Project World concepts;
- human-in-the-loop principles;
- AI safety and assurance in construction;
- interoperability proposals;
- selected research artifacts.

K6 exists to create credibility, recruiting leverage, distribution, community and standard-setting influence.

SFC may publicly explain the problem, the required properties of a solution and the governing principles while withholding the private implementation that delivers superior production performance.

---

## 10. SFC-K7 — Market Narrative

**Disclosure:** Public and broadly distributable.

Examples:

- website copy;
- sales material;
- social communication;
- press;
- conference positioning;
- investor/category narrative;
- product pages;
- brand assets.

Examples of appropriate K7 language include:

- **People and technology for construction delivery.**
- **Engineering-to-construction production.**
- **Model. Coordinate. Verify. Measure. Improve.**

K7 explains outcomes, category and value. It does not disclose sensitive algorithms or implementation detail.

---

## 11. Concept versus implementation

A public principle does not require a public implementation.

For example, SFC may publicly state that a determination is grounded in evidence and provenance while keeping private:

- ranking weights;
- failure thresholds;
- model-routing logic;
- advanced evidence-admission heuristics;
- internal scoring;
- private training examples;
- production optimizations.

Formally:

```text
Public Principle != Public Implementation
```

SFC should prefer publishing stable contracts and reference semantics while protecting the accumulated intelligence that produces superior results in real production.

---

## 12. Interface versus intelligence

Good candidates for deliberate exposure:

```text
Input format
Output format
Protocol
Schema
SDK
Connector interface
Reference behavior
```

Good candidates for protection:

```text
Optimization
Reasoning strategy
Ranking
Learning
Production data
Specialized models
Cross-project intelligence
```

The intended boundary is:

```text
OPEN CONTRACT
    +
PRIVATE ADVANTAGE
    +
ACCUMULATING DATA
```

---

## 13. Requirement Intelligence example

A canonical requirement contract may be public:

```text
Requirement {
  id
  source
  authority
  applicability
  condition
  evidence_required
}
```

SFC may also publish the required shape and semantic invariants of a valid determination.

The following may remain private when they provide material production advantage:

- how requirements are extracted at production quality;
- how applicability is resolved;
- how conflicting authorities are ranked;
- how project context is selected;
- how evidence is scored or prioritized;
- how ambiguous cases are routed or escalated;
- how accumulated corrections improve future execution.

This allows the market to adopt the language without receiving SFC's highest-performing implementation.

---

## 14. Classification decision test

Before creating, moving or publishing an artifact, its owner should answer:

1. **Does this asset accumulate strategic advantage?**  
   If disclosure would materially help a competitor replicate a difficult capability, prefer K0–K1.

2. **Does a customer need it to use or trust SFC?**  
   If yes, but broad publication is unnecessary, prefer K3.

3. **Does a partner or developer need it to build on SFC?**  
   If yes, prefer K4 or K5 depending on whether public adoption is desired.

4. **Does publication increase adoption, trust, developer activity or standard-setting more than it reduces SFC's moat?**  
   If yes, consider K5–K7.

A useful conceptual model is:

```text
ExposureDecision = f(
  StrategicValue,
  ReplicationRisk,
  AdoptionBenefit,
  TrustRequirement
)
```

---

## 15. Default classification examples

| Asset | Default class |
|---|---:|
| Logo / positioning | K7 |
| Project World concept | K6–K7 |
| Project World schema | K5 |
| Work Unit schema | K5 |
| Connector SDK | K5 |
| Evidence protocol | K5 |
| Basic determination reference | K5 |
| Public API documentation | K4–K5 |
| Customer audit report | K3 |
| Customer project state | K3 |
| Internal production dashboard | K2 |
| Production Planner internals | K1 |
| Advanced Requirement Compiler | K1 |
| Generative MEP scoring | K1 |
| Constructability heuristics | K0–K1 |
| Customer-derived corrections | K0 |
| Proprietary training/evaluation corpus | K0 |
| Specialized model weights | K0 |
| Pricing / margin intelligence | K0 |
| Credentials and secrets | K0 |

The table is a default, not an automatic entitlement to disclose. Actual ownership, contractual obligations, privacy, security, provenance and licensing must still be verified.

---

## 16. Artifact metadata

Internal SFC artifacts should carry classification metadata where practical.

Example restricted artifact:

```text
Classification: SFC-K1
Owner: Production Intelligence
Disclosure: Internal Restricted
External publication: Prohibited
```

Example public artifact:

```text
Classification: SFC-K5
Owner: Open Platform
Disclosure: Public
License: Apache-2.0
```

Repositories should define their maximum permitted exposure class. A public repository is not an acceptable storage location for an artifact classified K0–K4.

---

## 17. Promotion and disclosure review

Exposure is monotonic by default:

```text
K1 -> K5  requires deliberate disclosure review.
K5 -> K1  does not restore secrecy after publication.
```

Before increasing exposure, review at minimum:

- ownership and chain of title;
- customer and contractual restrictions;
- confidentiality obligations;
- privacy and data rights;
- security implications;
- open-source license implications;
- patentability / publication timing where relevant;
- competitive replication risk;
- strategic adoption benefit.

No employee or contributor should publish an internal SFC artifact merely because the repository or communication channel is convenient.

---

## 18. Public repository rule

The `systems-for-construction` repository is an open-source distribution and standards surface.

It should preferentially contain:

```text
category and principles
protocols and schemas
SDKs
reference connectors
reference runtime
interoperability
public conformance behavior
selected research and examples
```

It should not become the storage location for:

```text
customer data
private correction corpora
proprietary evaluations
commercial model weights
pricing intelligence
private production optimization
customer-specific learning
restricted security information
```

The fact that a concept has a public reference implementation does not require SFC's production implementation, optimization strategy or accumulated learning to be public.

---

## 19. Constitutional principle

SFC should publish enough knowledge to define useful industry contracts and attract an ecosystem, while preserving the accumulating capabilities that turn those contracts into superior production.

The intended equilibrium is:

```text
TRUST + ADOPTION + ECOSYSTEM
              without sacrificing
IP + DATA + LEARNING + ECONOMIC ADVANTAGE
```

This policy governs the exposure decision before code, documents, datasets, models, research or product knowledge cross an organizational boundary.
