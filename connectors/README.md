# Connectors

Connectors translate external systems into SFC contracts. The first public
interfaces are intentionally provider-neutral:

```text
Revit / IFC / PDF / API
          ↓
     ProjectWorld
          ↓
  SFC assurance runtime
```

The core does not import Autodesk, PDF, database or cloud SDKs. Concrete
connectors will be added under `connectors/ifc`, `connectors/pdf` and
`connectors/revit` as separate adapters.

