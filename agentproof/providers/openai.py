"""OpenAI provider implementation."""

from __future__ import annotations

from typing import Any

import httpx

from agentproof.errors import ProviderError
from agentproof.models import Usage
from agentproof.providers.base import LLMResponse, Provider, ProviderSpec
from agentproof.providers.http import HttpTransport

__all__ = ["OPENAI_SPEC", "OpenAIProvider"]


OPENAI_SPEC = ProviderSpec(
    name="openai",
    env_var="OPENAI_API_KEY",
    default_model="gpt-6.1-sol",
    default_base_url="https://api.openai.com",
    label="OpenAI",
)

#: Name used for the JSON schema response format.
SCHEMA_NAME = "agentproof_verification_report"


class OpenAIProvider(Provider):
    """Talk to the OpenAI Chat Completions API.

    Args:
        api_key: OpenAI API key.
        model: Model identifier to use.
        base_url: API root URL.
        timeout: Per-request timeout in seconds.
        max_retries: Number of retries for retryable failures.
        transport: Optional httpx transport, primarily useful for testing.
    """

    spec = OPENAI_SPEC

    def __init__(
        self,
        *,
        api_key: str,
        model: str = OPENAI_SPEC.default_model,
        base_url: str = OPENAI_SPEC.default_base_url,
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

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 8192,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Run a completion against the OpenAI Chat Completions API.

        Args:
            system: The system prompt.
            user: The user prompt.
            max_tokens: Maximum tokens to generate.
            temperature: Optional sampling temperature. Reasoning models reject
                non-default sampling parameters, so this is omitted unless
                explicitly provided.
            json_schema: Optional JSON schema for structured output.

        Returns:
            The provider response.
        """
        headers = {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "max_completion_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if temperature is not None:
            payload["temperature"] = temperature

        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": SCHEMA_NAME,
                    "strict": True,
                    "schema": json_schema,
                },
            }

        url = f"{self.base_url}/v1/chat/completions"
        try:
            data = self._transport.post_json(
                url, headers=headers, payload=payload, provider=self.spec.name
            )
        except ProviderError as exc:
            if exc.status_code == 400 and "response_format" in str(exc) and json_schema is not None:
                # The endpoint does not support structured outputs; retry with
                # plain JSON mode and rely on prompt-level instructions.
                payload["response_format"] = {"type": "json_object"}
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
    """Join every text message from an OpenAI response."""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    parts: list[str] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                # Some responses return content as a list of typed parts.
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        parts.append(str(part.get("text", "")))
    return "\n".join(part for part in parts if part)


def _extract_usage(data: dict[str, Any]) -> Usage:
    """Extract token accounting from an OpenAI response."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return Usage()
    return Usage(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )
