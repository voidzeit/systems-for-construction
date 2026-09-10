# Project World

`ProjectWorld` is a provider-neutral snapshot of project facts. It contains
elements, properties, geometry, relationships, metadata and source identity.
The current reference readers are JSON, a conservative IFC STEP reader and an
optional PDF page reader.

Connectors may understand different source systems, but they must preserve the
same distinction between an observed value and an inferred claim. Unsupported
source constructs remain unsupported until a connector can represent them with
provenance.
