"""Shared pytest fixtures for the AgentProof test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agentproof.config import Settings
from agentproof.models import Usage


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the real environment from leaking into tests."""
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "AGENTPROOF_PROVIDER",
        "AGENTPROOF_MODEL",
        "AGENTPROOF_TASK",
        "AGENTPROOF_CLAIM",
        "AGENTPROOF_WORKSPACE",
        "AGENTPROOF_MIN_CONFIDENCE",
        "AGENTPROOF_MAX_FILES",
        "AGENTPROOF_MAX_ARTIFACT_BYTES",
        "AGENTPROOF_MAX_TOTAL_BYTES",
        "AGENTPROOF_BASE_URL",
        "AGENTPROOF_AUDITOR_INSTRUCTIONS",
        "XDG_CONFIG_HOME",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a small workspace with a mix of useful and useless files."""
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "deploy.sh").write_text("#!/bin/sh\necho deploying\n", encoding="utf-8")
    (root / "notes.md").write_text("Deployed on 2026-10-20.\n", encoding="utf-8")
    (root / "run.log").write_text("step 1 ok\nstep 2 ok\n", encoding="utf-8")
    (root / "empty.txt").write_text("", encoding="utf-8")
    (root / "ignored").mkdir()
    (root / "ignored" / "cache.bin").write_bytes(b"\x00\x01\x02\x03")
    return root


@pytest.fixture
def settings() -> Settings:
    """Return a resolved settings object with test-friendly defaults."""
    return Settings(
        task="Create a deployment script and run the test suite.",
        claim="I created deploy.sh and all 42 tests pass.",
        provider="anthropic",
        model="claude-sonnet-5-5",
        min_confidence=0.75,
    )


def make_report_payload(
    *,
    verdict: str = "success",
    confidence: float = 0.9,
    summary: str = "Everything checks out.",
    checks: list[dict[str, str]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a payload shaped like the auditor's JSON response.

    Args:
        verdict: The verdict to report.
        confidence: The confidence score.
        summary: The summary text.
        checks: The requirement checks.
        **extra: Additional top-level fields.

    Returns:
        The payload dictionary.
    """
    payload: dict[str, Any] = {
        "verdict": verdict,
        "confidence": confidence,
        "summary": summary,
        "checks": checks
        if checks is not None
        else [
            {
                "requirement": "Create a deployment script",
                "status": "verified",
                "evidence": "deploy.sh exists and is executable",
                "source": "deploy.sh",
            }
        ],
        "discrepancies": [],
        "hallucinations": [],
        "missing_items": [],
        "recommendations": [],
        "notes": "",
    }
    payload.update(extra)
    return payload


@pytest.fixture
def report_payload() -> dict[str, Any]:
    """Return a successful audit payload."""
    return make_report_payload()


class FakeProvider:
    """A provider stub that returns canned text.

    Args:
        responses: Text payloads returned in order.
    """

    spec = type("Spec", (), {"name": "fake", "label": "Fake", "env_var": "FAKE_API_KEY"})()

    def __init__(self, responses: list[str]) -> None:
        """Store the canned responses the provider will replay."""
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def complete(self, **kwargs: Any) -> Any:
        """Record the call and return the next canned response."""
        self.calls.append(kwargs)
        text = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        from agentproof.providers.base import LLMResponse

        return LLMResponse(
            text=text,
            model="fake-model",
            provider="fake",
            usage=Usage(prompt_tokens=10, completion_tokens=20),
        )

    def close(self) -> None:
        """Mark the provider as closed."""
        self.closed = True


@pytest.fixture
def fake_provider() -> FakeProvider:
    """Return a provider stub with a single successful JSON response."""
    return FakeProvider([json.dumps(make_report_payload())])
