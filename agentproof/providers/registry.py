"""Provider registry and factory.

Keeping the provider list in one place lets the CLI offer a consistent choice
menu, resolve the right environment variable for credentials, and fall back to
sensible default models.
"""

from __future__ import annotations

from agentproof.errors import ConfigurationError, MissingCredentialsError
from agentproof.providers.anthropic import ANTHROPIC_SPEC, AnthropicProvider
from agentproof.providers.base import Provider, ProviderSpec
from agentproof.providers.openai import OPENAI_SPEC, OpenAIProvider

__all__ = [
    "PROVIDERS",
    "AnthropicProvider",
    "OpenAIProvider",
    "Provider",
    "ProviderSpec",
    "create_provider",
    "get_spec",
    "provider_names",
]

#: All supported providers, keyed by their canonical name.
PROVIDERS: dict[str, ProviderSpec] = {
    ANTHROPIC_SPEC.name: ANTHROPIC_SPEC,
    OPENAI_SPEC.name: OPENAI_SPEC,
}


def provider_names() -> list[str]:
    """Return the canonical names of every supported provider."""
    return sorted(PROVIDERS)


def get_spec(name: str) -> ProviderSpec:
    """Look up the metadata of a provider.

    Args:
        name: Canonical provider name.

    Returns:
        The provider specification.

    Raises:
        ConfigurationError: If the provider is unknown.
    """
    try:
        return PROVIDERS[name.strip().lower()]
    except KeyError as exc:
        known = ", ".join(provider_names())
        raise ConfigurationError(f"Unknown provider '{name}'. Known providers: {known}") from exc


def create_provider(
    *,
    provider: str,
    api_key: str | None,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = 120.0,
    max_retries: int = 3,
) -> Provider:
    """Instantiate a provider client.

    Args:
        provider: Canonical provider name.
        api_key: API key. When omitted, the provider's environment variable
            is consulted.
        model: Model identifier; defaults to the provider's recommendation.
        base_url: API root URL; defaults to the provider's public endpoint.
        timeout: Per-request timeout in seconds.
        max_retries: Number of retries for retryable failures.

    Returns:
        A ready-to-use provider client.

    Raises:
        MissingCredentialsError: If no API key can be resolved.
        ConfigurationError: If the provider name is unknown.
    """
    spec = get_spec(provider)
    resolved_key = (api_key or "").strip()
    if not resolved_key:
        import os

        resolved_key = os.environ.get(spec.env_var, "").strip()
    if not resolved_key:
        raise MissingCredentialsError(spec.name, spec.env_var)

    resolved_model = (model or "").strip() or spec.default_model
    resolved_base = (base_url or "").strip() or spec.default_base_url

    if spec.name == ANTHROPIC_SPEC.name:
        return AnthropicProvider(
            api_key=resolved_key,
            model=resolved_model,
            base_url=resolved_base,
            timeout=timeout,
            max_retries=max_retries,
        )
    return OpenAIProvider(
        api_key=resolved_key,
        model=resolved_model,
        base_url=resolved_base,
        timeout=timeout,
        max_retries=max_retries,
    )
