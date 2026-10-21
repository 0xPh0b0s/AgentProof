"""Anthropic (Claude) provider implementation."""

from __future__ import annotations

from typing import Any

import httpx

from agentproof.errors import ProviderError
from agentproof.models import Usage
from agentproof.providers.base import LLMResponse, Provider, ProviderSpec
from agentproof.providers.http import HttpTransport

__all__ = ["ANTHROPIC_SPEC", "AnthropicProvider"]


ANTHROPIC_SPEC = ProviderSpec(
    name="anthropic",
    env_var="ANTHROPIC_API_KEY",
    default_model="claude-sonnet-5-5",
    default_base_url="https://api.anthropic.com",
    label="Anthropic Claude",
)

#: Models that accept the ``output_config.format`` JSON schema parameter.
STRUCTURED_OUTPUT_MODELS: frozenset[str] = frozenset(
    {
        "claude-fable-5-1",
        "claude-mythos-5-1",
        "claude-fable-5",
        "claude-mythos-5",
        "claude-mythos-preview",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-opus-4-5-20251101",
        "claude-sonnet-5-5",
        "claude-sonnet-5",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5",
        "claude-sonnet-4-5-20250929",
        "claude-haiku-5-5",
        "claude-haiku-4-5",
        "claude-haiku-4-5-20251001",
    }
)

#: The Anthropic API version header sent with every request.
API_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    """Talk to the Anthropic Messages API.

    Args:
        api_key: Anthropic API key.
        model: Model identifier to use.
        base_url: API root URL.
        timeout: Per-request timeout in seconds.
        max_retries: Number of retries for retryable failures.
        transport: Optional httpx transport, primarily useful for testing.
    """

    spec = ANTHROPIC_SPEC

    def __init__(
        self,
        *,
        api_key: str,
        model: str = ANTHROPIC_SPEC.default_model,
        base_url: str = ANTHROPIC_SPEC.default_base_url,
        timeout: float = 120.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Store the connection settings and prepare the HTTP transport."""
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._transport = HttpTransport(
            timeout=timeout, max_retries=max_retries, transport=transport
        )

    @property
    def supports_structured_output(self) -> bool:
        """Whether the configured model accepts a JSON schema output format."""
        return self.model in STRUCTURED_OUTPUT_MODELS

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 8192,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Run a completion against the Anthropic Messages API.

        Args:
            system: The system prompt.
            user: The user prompt.
            max_tokens: Maximum tokens to generate.
            temperature: Optional sampling temperature. Recent Claude models
                reject non-default sampling parameters, so this is omitted
                unless explicitly provided.
            json_schema: Optional JSON schema for structured output.

        Returns:
            The provider response.
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if temperature is not None:
            payload["temperature"] = temperature

        use_schema = json_schema is not None and self.supports_structured_output
        if use_schema and json_schema is not None:
            payload["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}

        url = f"{self.base_url}/v1/messages"
        try:
            data = self._transport.post_json(
                url, headers=headers, payload=payload, provider=self.spec.name
            )
        except ProviderError as exc:
            if use_schema and exc.status_code == 400 and "output_config" in str(exc):
                # The endpoint does not support structured outputs; retry
                # without it and rely on prompt-level JSON instructions.
                payload.pop("output_config", None)
                data = self._transport.post_json(
                    url, headers=headers, payload=payload, provider=self.spec.name
                )
            else:
                raise

        return LLMResponse(
            text=_extract_text(data),
            model=str(data.get("model") or self.model),
            provider=self.spec.name,
            usage=_extract_usage(data),
            raw=data,
        )

    def close(self) -> None:
        """Close the underlying HTTP transport."""
        self._transport.close()


def _extract_text(data: dict[str, Any]) -> str:
    """Join every text content block from an Anthropic response."""
    blocks = data.get("content")
    if not isinstance(blocks, list):
        return ""
    parts = [
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(part for part in parts if part)


def _extract_usage(data: dict[str, Any]) -> Usage:
    """Extract token accounting from an Anthropic response."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return Usage()
    return Usage(
        prompt_tokens=int(usage.get("input_tokens") or 0),
        completion_tokens=int(usage.get("output_tokens") or 0),
    )
