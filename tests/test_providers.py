"""Tests for the provider implementations."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from agentproof.errors import MissingCredentialsError, ProviderError
from agentproof.providers.anthropic import AnthropicProvider
from agentproof.providers.openai import OpenAIProvider
from agentproof.providers.registry import create_provider, get_spec, provider_names

ANTHROPIC_BODY: dict[str, Any] = {
    "model": "claude-sonnet-5-5",
    "content": [
        {"type": "thinking", "thinking": "hmm", "signature": "sig"},
        {"type": "text", "text": '{"verdict": "success"}'},
    ],
    "usage": {"input_tokens": 11, "output_tokens": 7},
}

OPENAI_BODY: dict[str, Any] = {
    "model": "gpt-6.1-sol",
    "choices": [{"message": {"role": "assistant", "content": '{"verdict": "failed"}'}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 9},
}


def test_provider_names() -> None:
    """Both providers are registered."""
    assert provider_names() == ["anthropic", "openai"]


def test_get_spec_rejects_unknown() -> None:
    """An unknown provider name is rejected."""
    with pytest.raises(Exception, match="Unknown provider"):
        get_spec("nope")


def test_create_provider_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing API key produces a clear error."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingCredentialsError) as excinfo:
        create_provider(provider="anthropic", api_key=None)
    assert excinfo.value.env_var == "ANTHROPIC_API_KEY"


def test_create_provider_uses_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider's environment variable is used when no key is given."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = create_provider(provider="openai", api_key=None)
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-6.1-sol"


def test_anthropic_request_shape() -> None:
    """The Anthropic request carries the expected headers and body."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(200, json=ANTHROPIC_BODY)

    provider = AnthropicProvider(
        api_key="k",
        transport=httpx.MockTransport(handler),
    )
    response = provider.complete(
        system="sys",
        user="usr",
        max_tokens=1024,
        json_schema={"type": "object"},
    )

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "k"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["json"]["model"] == "claude-sonnet-5-5"
    assert captured["json"]["max_tokens"] == 1024
    assert captured["json"]["system"] == "sys"
    assert captured["json"]["output_config"]["format"]["type"] == "json_schema"
    # Non-default sampling parameters are rejected by current Claude models.
    assert "temperature" not in captured["json"]

    assert response.text == '{"verdict": "success"}'
    assert response.usage.prompt_tokens == 11
    assert response.usage.completion_tokens == 7


def test_anthropic_omits_structured_output_for_unknown_models() -> None:
    """Models without structured-output support fall back to prompt JSON."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=ANTHROPIC_BODY)

    provider = AnthropicProvider(
        api_key="k",
        model="claude-some-legacy-model",
        transport=httpx.MockTransport(handler),
    )
    provider.complete(system="s", user="u", json_schema={"type": "object"})

    assert "output_config" not in captured["json"]


def test_anthropic_falls_back_when_structured_output_is_rejected() -> None:
    """A 400 mentioning output_config triggers a plain retry."""
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "output_config" in body:
            return httpx.Response(
                400,
                json={"error": {"message": "output_config is not supported"}},
            )
        return httpx.Response(200, json=ANTHROPIC_BODY)

    provider = AnthropicProvider(api_key="k", transport=httpx.MockTransport(handler))
    response = provider.complete(system="s", user="u", json_schema={"type": "object"})

    assert len(calls) == 2
    assert "output_config" not in calls[1]
    assert response.text == '{"verdict": "success"}'


def test_openai_request_shape() -> None:
    """The OpenAI request carries the expected headers and body."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(200, json=OPENAI_BODY)

    provider = OpenAIProvider(api_key="k", transport=httpx.MockTransport(handler))
    response = provider.complete(
        system="sys",
        user="usr",
        max_tokens=512,
        json_schema={"type": "object"},
    )

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer k"
    assert captured["json"]["model"] == "gpt-6.1-sol"
    assert captured["json"]["max_completion_tokens"] == 512
    assert captured["json"]["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["json"]["response_format"]["type"] == "json_schema"

    assert response.text == '{"verdict": "failed"}'
    assert response.usage.prompt_tokens == 5


def test_provider_errors_are_surfaced() -> None:
    """A non-retryable HTTP error raises a ProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    provider = AnthropicProvider(api_key="bad", transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError) as excinfo:
        provider.complete(system="s", user="u")
    assert excinfo.value.status_code == 401
    assert "invalid api key" in str(excinfo.value)


def test_retryable_errors_are_retried() -> None:
    """A 500 is retried and can succeed on a later attempt."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return httpx.Response(200, json=ANTHROPIC_BODY)

    provider = AnthropicProvider(
        api_key="k",
        max_retries=2,
        transport=httpx.MockTransport(handler),
    )
    provider.complete(system="s", user="u")

    assert attempts["count"] == 2
