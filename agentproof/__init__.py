"""AgentProof - independent verification that an AI agent did what it claimed.

The package exposes a small, stable public API:

>>> from agentproof import Settings, VerificationReport, Verdict
>>> Verdict.SUCCESS.label
'SUCCESS'
"""

from __future__ import annotations

__version__ = "1.0.0"

from agentproof.config import Settings
from agentproof.context import VerificationContext, build_context
from agentproof.errors import (
    AgentProofError,
    ConfigurationError,
    MissingCredentialsError,
    ProviderError,
    ResponseParseError,
    VerificationError,
    WorkspaceError,
)
from agentproof.models import CheckStatus, Verdict, VerificationCheck, VerificationReport

__all__ = [
    "AgentProofError",
    "CheckStatus",
    "ConfigurationError",
    "MissingCredentialsError",
    "ProviderError",
    "ResponseParseError",
    "Settings",
    "Verdict",
    "VerificationCheck",
    "VerificationContext",
    "VerificationError",
    "VerificationReport",
    "WorkspaceError",
    "__version__",
    "build_context",
]
