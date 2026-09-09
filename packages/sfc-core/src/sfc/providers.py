"""Provider-neutral interfaces for agent and vision adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderRequest:
    prompt: str
    model: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    requested_model: str | None
    observed_model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None


class EngineeringProvider(Protocol):
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Return a proposal; callers decide whether it is evidence."""


class VisionProvider(Protocol):
    def inspect(self, request: ProviderRequest) -> ProviderResponse:
        """Return a visual observation proposal with source provenance added by the adapter."""

