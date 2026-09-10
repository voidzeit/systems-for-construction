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

## The event log is the only durable state

The control plane and the evidence room are both in-memory reference services.
Neither is the source of truth; the append-only log is, and both are reductions
of it:

```text
                            EventLog
                               |
                +--------------+--------------+
                |                             |
          ControlPlane                  EvidenceRoom
        obligations, work,          document versions,
        reviews, value              evidence state history
```

`from_events` on either projection applies the same domain rules as live
execution, so a log recording an invalid sequence fails to replay rather than
reconstructing a state the rules forbid. An event type the build does not
recognize is refused outright: a reducer that skipped it would report a
successful replay of a log whose unread events may have been state-affecting.

What the log is not yet: tamper-evident. It is append-only by convention, not
by construction - removing a line leaves no trace. A hash chain and stream
versioning for concurrent writers belong to a durable deployment layer, and are
recorded as such rather than implied here.

The initial implementation uses JSON files to keep the reference workflow inspectable. A database, object store or durable workflow engine may be added behind an adapter without changing the contracts.

