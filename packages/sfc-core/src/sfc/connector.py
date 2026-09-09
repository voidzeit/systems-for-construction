"""Connector boundary: external systems produce ProjectWorld snapshots."""

from __future__ import annotations

from typing import Protocol

from .models import ProjectWorld


class ProjectWorldConnector(Protocol):
    connector_id: str

    def snapshot(self, source: str) -> ProjectWorld:
        """Extract a provider-neutral, provenance-bearing Project World."""

