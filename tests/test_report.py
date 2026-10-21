"""Tests for report rendering."""

from __future__ import annotations

import json

from agentproof.models import (
    CheckStatus,
    Verdict,
    VerificationCheck,
    VerificationReport,
)
from agentproof.report import render_json_report, render_report
from rich.console import Console


def _report(verdict: Verdict = Verdict.SUCCESS) -> VerificationReport:
    """Build a representative report."""
    return VerificationReport(
        verdict=verdict,
        confidence=0.87,
        summary="The agent completed the deployment script but not the tests.",
        checks=[
            VerificationCheck(
                requirement="Create deploy.sh",
                status=CheckStatus.VERIFIED,
                evidence="deploy.sh exists and runs",
                source="deploy.sh",
            ),
            VerificationCheck(
                requirement="Run the test suite",
                status=CheckStatus.MISSING,
                evidence="No test output was produced",
                source="",
            ),
        ],
        discrepancies=["Claim mentions 42 passing tests, no test output exists."],
        hallucinations=["The agent claimed to have run the suite."],
        missing_items=["Test run output"],
        recommendations=["Run the suite and save the output."],
        notes="Confidence is limited by the sparse workspace.",
        provider="anthropic",
        model="claude-sonnet-5-5",
        artifacts_scanned=4,
        prompt_tokens=100,
        completion_tokens=50,
    )


def test_render_report_shows_the_badge() -> None:
    """The report contains the status badge and the confidence score."""
    console = Console(record=True, width=120, no_color=True)

    render_report(_report(), console)

    output = console.export_text()
    assert "SUCCESS" in output
    assert "87%" in output
    assert "Create deploy.sh" in output
    assert "Test run output" in output
    assert "claude-sonnet-5-5" in output


def test_render_report_shows_failed_badge() -> None:
    """A failed verdict is rendered with the FAILED badge."""
    console = Console(record=True, width=120, no_color=True)

    render_report(_report(Verdict.FAILED), console)

    output = console.export_text()
    assert "FAILED" in output


def test_render_json_report_emits_valid_json() -> None:
    """The JSON output mode produces machine-readable output."""
    console = Console(record=True, width=120, no_color=True)

    render_json_report(_report(), console)

    payload = json.loads(console.export_text())
    assert payload["verdict"] == "success"
    assert payload["confidence"] == 0.87
    assert len(payload["checks"]) == 2
    assert payload["usage"]["prompt_tokens"] == 100


def test_report_counts() -> None:
    """The report counts satisfied and unsatisfied requirements."""
    report = _report()

    assert report.verified_count == 1
    assert report.failed_count == 1
