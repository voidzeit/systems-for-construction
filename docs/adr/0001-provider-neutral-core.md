# ADR 0001: Keep the core provider-neutral

Status: accepted

SFC domain contracts must run without FastAPI, Postgres, Autodesk SDKs, cloud
SDKs or a model provider. Integrations translate into the contracts at the
boundary. This keeps IFC, Revit, PDF, API and future connectors interchangeable.

