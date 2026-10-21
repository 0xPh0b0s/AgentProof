"""Typed data structures shared across the AgentProof pipeline.

The models in this module are the contract between the verification engine,
the LLM providers and the reporting layer. They are intentionally plain
dataclasses with explicit ``to_dict`` serialisation so the JSON output mode is
fully under our control (and stays stable for CI consumers).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """The overall outcome of a verification run.

    AgentProof deliberately uses a binary verdict: the burden of proof lies
    with the agent, so anything short of complete, evidenced success is a
    failure.
    """

    SUCCESS = "success"
    FAILED = "failed"

    @property
    def label(self) -> str:
        """Return the uppercase badge text used in terminal output."""
        return "SUCCESS" if self is Verdict.SUCCESS else "FAILED"


class CheckStatus(str, Enum):
    """The state of a single requirement discovered during the audit."""

    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    MISSING = "missing"
    UNVERIFIABLE = "unverifiable"

    @property
    def is_satisfied(self) -> bool:
        """Return ``True`` when the requirement is fully met and evidenced."""
        return self is CheckStatus.VERIFIED


#: Check statuses that prevent a requirement from counting as met.
UNSATISFIED_STATUSES: frozenset[CheckStatus] = frozenset(
    {
        CheckStatus.PARTIAL,
        CheckStatus.FAILED,
        CheckStatus.MISSING,
        CheckStatus.UNVERIFIABLE,
    }
)


@dataclass(slots=True)
class VerificationCheck:
    """A single requirement extracted from the task, with its audit outcome.

    Attributes:
        requirement: The requirement text, restated by the auditor.
        status: Whether the requirement was satisfied by the artifacts.
        evidence: Concrete evidence supporting the status.
        source: Artifact path (or similar locator) the evidence came from.
    """

    requirement: str
    status: CheckStatus
    evidence: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise the check to a JSON-compatible dictionary."""
        return {
            "requirement": self.requirement,
            "status": self.status.value,
            "evidence": self.evidence,
            "source": self.source,
        }


@dataclass(slots=True)
class VerificationReport:
    """The complete result of a verification run.

    Attributes:
        verdict: Overall success/failure outcome.
        confidence: Auditor confidence in the verdict, between 0.0 and 1.0.
        summary: Short natural-language justification of the verdict.
        checks: Per-requirement audit results.
        discrepancies: Statements in the claim contradicted by the artifacts.
        hallucinations: Claimed outcomes with no supporting evidence at all.
        missing_items: Requirements with no corresponding work product.
        recommendations: Suggested next steps for the agent's owner.
        notes: Free-form remarks from the auditor.
        provider: Name of the provider that produced the verdict.
        model: Model identifier used for the audit.
        artifacts_scanned: Number of artifacts included in the audit prompt.
        prompt_tokens: Prompt tokens consumed, when reported by the provider.
        completion_tokens: Completion tokens consumed, when reported.
    """

    verdict: Verdict
    confidence: float
    summary: str
    checks: list[VerificationCheck] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)
    hallucinations: list[str] = field(default_factory=list)
    missing_items: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    notes: str = ""
    provider: str = ""
    model: str = ""
    artifacts_scanned: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def verified_count(self) -> int:
        """Number of requirements confirmed as satisfied."""
        return sum(1 for check in self.checks if check.status.is_satisfied)

    @property
    def failed_count(self) -> int:
        """Number of requirements that were not satisfied."""
        return sum(1 for check in self.checks if check.status in UNSATISFIED_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the report to a JSON-compatible dictionary."""
        return {
            "verdict": self.verdict.value,
            "confidence": round(self.confidence, 4),
            "summary": self.summary,
            "checks": [check.to_dict() for check in self.checks],
            "discrepancies": list(self.discrepancies),
            "hallucinations": list(self.hallucinations),
            "missing_items": list(self.missing_items),
            "recommendations": list(self.recommendations),
            "notes": self.notes,
            "provider": self.provider,
            "model": self.model,
            "artifacts_scanned": self.artifacts_scanned,
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
            },
        }


@dataclass(slots=True)
class Usage:
    """Token accounting reported by a provider."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total number of tokens consumed by the request."""
        return self.prompt_tokens + self.completion_tokens
