# ADR 0006: Protocol surfaces start read-only

Status: accepted

The reference MCP gateway and local HTTP API expose inspection and query
operations only. Mutation will be introduced through explicit application
services with policy, human authority and append-only audit events.

