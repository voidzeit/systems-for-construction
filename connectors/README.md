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

The core does not import Autodesk, PDF, database or cloud SDKs. The reference
package includes dependency-free STEP extraction in `sfc.ifc` and optional PDF
text extraction in `sfc.pdf`; concrete connectors belong under
`connectors/ifc`, `connectors/pdf` and `connectors/revit` as separate adapters.
