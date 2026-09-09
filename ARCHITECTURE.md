# SFC architecture

SFC is organized as four planes:

```text
Applications: Studio · reports · field · billing
Intelligence/control: agents · obligations · policy · proof · review
Project World: BIM · IFC · drawings · schedules · documents · field data
Protocols/integrations: MCP · APIs · events · Revit · Procore · ERP
```

The dependency direction is inward:

```text
connectors/providers/apps → application services → SFC domain
```

The domain can run without FastAPI, Postgres, GCP, Autodesk or a model provider. A connector creates a `ProjectWorld`; an agent can propose evidence; `EvidenceAuthority` admits evidence; deterministic assurance creates a `Determination`; `RunStore` validates and publishes a canonical run.

The initial implementation uses JSON files to keep the reference workflow inspectable. A database, object store or durable workflow engine may be added behind an adapter without changing the contracts.

