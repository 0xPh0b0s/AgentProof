"""Tests for the verification engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentproof.config import Settings
from agentproof.context import VerificationContext, build_context
from agentproof.errors import ResponseParseError
from agentproof.models import CheckStatus, Verdict
from agentproof.verifier import Verifier, parse_report_payload, parse_report_text

from .conftest import FakeProvider, make_report_payload


def _context(workspace: Path, settings: Settings) -> VerificationContext:
    """Build a verification context for the test workspace."""
    return build_context(
        settings,
        task="Create a deployment script and run the test suite.",
        claim="I created deploy.sh and all 42 tests pass.",
        workspace=workspace,
    )


def test_successful_audit_returns_success(workspace: Path, settings: Settings) -> None:
    """A successful audit produces a SUCCESS verdict."""
    provider = FakeProvider([json.dumps(make_report_payload())])
    verifier = Verifier(provider, settings)

    report = verifier.verify(_context(workspace, settings))

    assert report.verdict is Verdict.SUCCESS
    assert report.confidence == pytest.approx(0.9)
    assert report.verified_count == 1
    assert report.provider == "fake"
    assert report.artifacts_scanned > 0


def test_failed_audit_returns_failed(workspace: Path, settings: Settings) -> None:
    """A failing audit produces a FAILED verdict."""
    payload = make_report_payload(
        verdict="failed",
        confidence=0.95,
        checks=[
            {
                "requirement": "Run the test suite",
                "status": "missing",
                "evidence": "No test output present",
                "source": "",
            }
        ],
    )
    provider = FakeProvider([json.dumps(payload)])
    verifier = Verifier(provider, settings)

    report = verifier.verify(_context(workspace, settings))

    assert report.verdict is Verdict.FAILED
    assert report.failed_count == 1


def test_low_confidence_success_is_downgraded(workspace: Path, settings: Settings) -> None:
    """A SUCCESS verdict below the threshold is downgraded to FAILED."""
    payload = make_report_payload(verdict="success", confidence=0.4)
    provider = FakeProvider([json.dumps(payload)])
    verifier = Verifier(provider, settings)

    report = verifier.verify(_context(workspace, settings))

    assert report.verdict is Verdict.FAILED
    assert "below the required threshold" in report.notes


def test_success_with_unsatisfied_checks_is_downgraded(workspace: Path, settings: Settings) -> None:
    """A SUCCESS verdict with unsatisfied checks is downgraded to FAILED."""
    payload = make_report_payload(
        verdict="success",
        confidence=0.99,
        checks=[
            {
                "requirement": "Create deploy.sh",
                "status": "verified",
                "evidence": "present",
                "source": "deploy.sh",
            },
            {
                "requirement": "Run the tests",
                "status": "missing",
                "evidence": "no output",
                "source": "",
            },
        ],
    )
    provider = FakeProvider([json.dumps(payload)])
    verifier = Verifier(provider, settings)

    report = verifier.verify(_context(workspace, settings))

    assert report.verdict is Verdict.FAILED
    assert "requirement(s) remained unsatisfied" in report.notes


def test_success_without_checks_is_downgraded(workspace: Path, settings: Settings) -> None:
    """A SUCCESS verdict with no requirement-level checks is unproven."""
    payload = make_report_payload(verdict="success", confidence=0.99, checks=[])
    provider = FakeProvider([json.dumps(payload)])
    verifier = Verifier(provider, settings)

    report = verifier.verify(_context(workspace, settings))

    assert report.verdict is Verdict.FAILED
    assert "without any requirement-level checks" in report.notes
    assert "summary alone" not in report.notes


def test_failed_without_checks_keeps_summary_note(workspace: Path, settings: Settings) -> None:
    """An auditor-declared FAILED with no checks is annotated, not re-downgraded."""
    payload = make_report_payload(verdict="failed", confidence=0.99, checks=[])
    provider = FakeProvider([json.dumps(payload)])
    verifier = Verifier(provider, settings)

    report = verifier.verify(_context(workspace, settings))

    assert report.verdict is Verdict.FAILED
    assert "rests on its summary alone" in report.notes
    assert "without any requirement-level checks" not in report.notes


def test_report_records_evidence_completeness(workspace: Path, settings: Settings) -> None:
    """The report records whether the auditor saw all available evidence."""
    settings.max_files = 1
    provider = FakeProvider([json.dumps(make_report_payload())])
    verifier = Verifier(provider, settings)

    report = verifier.verify(_context(workspace, settings))

    assert report.artifacts_scanned == 1
    assert report.artifacts_skipped > 0
    assert report.budget_exhausted is True


def test_invalid_json_triggers_a_corrective_retry(workspace: Path, settings: Settings) -> None:
    """A malformed first answer is retried once with a reminder."""
    provider = FakeProvider(
        [
            "I could not comply, here is some prose.",
            json.dumps(make_report_payload()),
        ]
    )
    verifier = Verifier(provider, settings)

    report = verifier.verify(_context(workspace, settings))

    assert report.verdict is Verdict.SUCCESS
    assert len(provider.calls) == 2
    assert "could not be parsed as JSON" in provider.calls[1]["user"]


def test_unparseable_response_raises(workspace: Path, settings: Settings) -> None:
    """Two unparseable answers raise a clear error."""
    provider = FakeProvider(["still not json"])
    verifier = Verifier(provider, settings)

    with pytest.raises(ResponseParseError):
        verifier.verify(_context(workspace, settings))


def test_json_wrapped_in_prose_is_accepted(workspace: Path, settings: Settings) -> None:
    """A JSON object wrapped in prose is still parsed."""
    provider = FakeProvider(
        ["Here is my report:\n```json\n" + json.dumps(make_report_payload()) + "\n```"]
    )
    verifier = Verifier(provider, settings)

    report = verifier.verify(_context(workspace, settings))

    assert report.verdict is Verdict.SUCCESS


def test_parse_report_text_rejects_empty() -> None:
    """An empty response is rejected."""
    with pytest.raises(ResponseParseError):
        parse_report_text("   ")


def test_parse_report_payload_rejects_bad_verdict() -> None:
    """An unknown verdict is rejected."""
    with pytest.raises(ResponseParseError, match="invalid verdict"):
        parse_report_payload({"verdict": "maybe", "confidence": 0.5})


def test_parse_report_payload_coerces_values() -> None:
    """Values are coerced into their expected types."""
    report = parse_report_payload(
        {
            "verdict": "SUCCESS",
            "confidence": "85",
            "summary": "ok",
            "checks": [
                {
                    "requirement": "do it",
                    "status": "pass",
                    "evidence": "evidence",
                    "source": "file.txt",
                }
            ],
        }
    )

    assert report.verdict is Verdict.SUCCESS
    assert report.confidence == pytest.approx(0.85)
    assert report.checks[0].status is CheckStatus.VERIFIED


def test_parse_report_payload_handles_missing_fields() -> None:
    """Missing optional fields fall back to safe defaults."""
    report = parse_report_payload({"verdict": "failed", "confidence": 0.1})

    assert report.verdict is Verdict.FAILED
    assert report.checks == []
    assert report.summary == ""


def test_unknown_check_status_becomes_unverifiable() -> None:
    """An unknown check status is treated as unverifiable."""
    report = parse_report_payload(
        {
            "verdict": "failed",
            "confidence": 0.2,
            "checks": [{"requirement": "x", "status": "banana"}],
        }
    )

    assert report.checks[0].status is CheckStatus.UNVERIFIABLE
