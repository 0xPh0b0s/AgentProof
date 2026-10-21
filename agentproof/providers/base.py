"""Provider abstraction used by the verification engine.

Each provider turns a system prompt plus a user prompt into a text
completion. Keeping the surface this small means new backends can be added
without touching the verification logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agentproof.models import Usage

__all__ = ["LLMResponse", "Provider", "ProviderSpec"]


@dataclass(slots=True)
class LLMResponse:
    """A raw completion returned by a provider.

    Attributes:
        text: The model's text output.
        model: The model identifier that produced the output.
        provider: The provider that served the request.
        usage: Token accounting, when the provider reports it.
        raw: The untouched provider payload, for debugging.
    """

    text: str
    model: str
    provider: str
    usage: Usage = field(default_factory=Usage)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """Static metadata describing a supported LLM backend.

    Attributes:
        name: Short provider name, e.g. ``"anthropic"``.
        env_var: Environment variable holding the API key.
        default_model: Model used when the user does not pick one.
        default_base_url: Default API endpoint.
        label: Human-readable provider name.
    """

    name: str
    env_var: str
    default_model: str
    default_base_url: str
    label: str


class Provider(ABC):
    """Interface implemented by every LLM backend.

    Attributes:
        spec: Static metadata about the provider.
    """

    spec: ProviderSpec

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 8192,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Run a single completion.

        Args:
            system: The system prompt defining the auditor's role.
            user: The user prompt carrying the audit material.
            max_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature. ``None`` omits the parameter,
                which is required by several current models.
            json_schema: Optional JSON schema for structured output.

        Returns:
            The provider response.
        """
        raise NotImplementedError

    def close(self) -> None:
        """Release any resources held by the provider."""
        return None
