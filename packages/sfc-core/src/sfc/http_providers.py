"""Small HTTP provider adapters with no vendor SDK dependency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .providers import ProviderRequest, ProviderResponse, ToolCall


class ProviderError(RuntimeError):
    pass


def _post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ProviderError(f"provider request failed: {error}") from error


@dataclass
class OpenAICompatibleProvider:
    base_url: str
    api_key: str | None = None
    default_model: str = ""

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        payload = {"model": request.model or self.default_model, "messages": [{"role": "user", "content": request.prompt}]}
        if request.tools:
            payload["tools"] = [{"type": "function", "function": {"name": tool["name"], "description": tool.get("description", ""), "parameters": tool.get("input_schema", {"type": "object"})}} for tool in request.tools]
        body = _post(self.base_url.rstrip("/") + "/chat/completions", {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}, payload)
        choice = body.get("choices", [{}])[0]
        usage = body.get("usage", {})
        calls = tuple(ToolCall(item.get("id", "tool-call"), item.get("function", {}).get("name", ""), json.loads(item.get("function", {}).get("arguments", "{}"))) for item in choice.get("message", {}).get("tool_calls", []))
        return ProviderResponse(choice.get("message", {}).get("content", ""), payload["model"], body.get("model"), usage.get("prompt_tokens"), usage.get("completion_tokens"), calls)


@dataclass
class AnthropicProvider:
    api_key: str
    base_url: str = "https://api.anthropic.com"
    default_model: str = "claude-3-5-sonnet-latest"

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self.default_model
        payload = {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": request.prompt}]}
        if request.tools:
            payload["tools"] = [{"name": tool["name"], "description": tool.get("description", ""), "input_schema": tool.get("input_schema", {"type": "object"})} for tool in request.tools]
        body = _post(self.base_url.rstrip("/") + "/v1/messages", {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, payload)
        content = next((item for item in body.get("content", []) if item.get("type") == "text"), {})
        usage = body.get("usage", {})
        calls = tuple(ToolCall(item.get("id", "tool-call"), item.get("name", ""), item.get("input", {})) for item in body.get("content", []) if item.get("type") == "tool_use")
        return ProviderResponse(content.get("text", ""), model, body.get("model"), usage.get("input_tokens"), usage.get("output_tokens"), calls)


@dataclass
class GeminiProvider:
    api_key: str
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    default_model: str = "gemini-2.5-flash"

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self.default_model
        url = f"{self.base_url.rstrip('/')}/models/{model}:generateContent?key={self.api_key}"
        payload: dict[str, Any] = {"contents": [{"parts": [{"text": request.prompt}]}]}
        if request.tools:
            payload["tools"] = [{"function_declarations": [{
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object"}),
            } for tool in request.tools]}]
        body = _post(url, {}, payload)
        candidates = body.get("candidates", [{}])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        usage = body.get("usageMetadata", {})
        calls = tuple(ToolCall(f"tool-call-{index}", part.get("functionCall", {}).get("name", ""), part.get("functionCall", {}).get("args", {})) for index, part in enumerate(parts) if part.get("functionCall"))
        return ProviderResponse("".join(part.get("text", "") for part in parts), model, model, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"), calls)


def provider_from_environment() -> OpenAICompatibleProvider | AnthropicProvider | GeminiProvider:
    """Build a provider only when the caller explicitly configures one."""
    provider = os.environ.get("SFC_PROVIDER", "openai-compatible")
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("ANTHROPIC_API_KEY is required for SFC_PROVIDER=anthropic")
        return AnthropicProvider(key, default_model=os.environ.get("SFC_MODEL", "claude-3-5-sonnet-latest"))
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ProviderError("GEMINI_API_KEY is required for SFC_PROVIDER=gemini")
        return GeminiProvider(key, default_model=os.environ.get("SFC_MODEL", "gemini-2.5-flash"))
    return OpenAICompatibleProvider(os.environ.get("SFC_BASE_URL", "https://api.openai.com/v1"), os.environ.get("OPENAI_API_KEY"), os.environ.get("SFC_MODEL", "gpt-4o-mini"))
