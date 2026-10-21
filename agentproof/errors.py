"""Exception hierarchy for AgentProof.

Every error raised by the package derives from :class:`AgentProofError` so the
CLI can translate failures into friendly messages and well-defined exit codes
instead of dumping tracebacks at the user.
"""

from __future__ import annotations


class AgentProofError(Exception):
    """Base class for every error raised by AgentProof."""


class ConfigurationError(AgentProofError):
    """Raised when configuration is missing, malformed, or contradictory."""


class MissingCredentialsError(ConfigurationError):
    """Raised when no API key can be resolved for the selected provider.

    Attributes:
        provider: Name of the provider whose credentials are missing.
        env_var: Environment variable that holds the credential.
    """

    def __init__(self, provider: str, env_var: str) -> None:
        """Store the provider and the environment variable that holds its key."""
        self.provider = provider
        self.env_var = env_var
        super().__init__(
            f"No API key found for provider '{provider}'. Set the {env_var} "
            f"environment variable, add it to a .env file, or run 'agentproof init'."
        )


class WorkspaceError(AgentProofError):
    """Raised when the workspace or an artifact path cannot be read."""


class ProviderError(AgentProofError):
    """Raised when an LLM provider request fails.

    Attributes:
        provider: Name of the provider that failed.
        status_code: HTTP status code, when the failure was an HTTP error.
    """

    def __init__(self, message: str, *, provider: str, status_code: int | None = None) -> None:
        """Store the provider name and the HTTP status code, when known."""
        self.provider = provider
        self.status_code = status_code
        super().__init__(message)


class RateLimitError(ProviderError):
    """Raised when a provider rate limit is exhausted after all retries."""


class ResponseParseError(AgentProofError):
    """Raised when the auditor's response cannot be parsed into a report.

    Attributes:
        snippet: A short excerpt of the offending payload, for debugging.
    """

    def __init__(self, message: str, *, snippet: str = "") -> None:
        """Store a short excerpt of the offending payload."""
        self.snippet = snippet
        super().__init__(message)


class VerificationError(AgentProofError):
    """Raised when the verification workflow cannot be completed."""
