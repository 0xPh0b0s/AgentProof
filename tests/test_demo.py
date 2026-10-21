"""Tests for the built-in demonstration mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentproof.cli import EXIT_FAILED, main
from agentproof.demo import (
    DEMO_CLAIM,
    DEMO_FILES,
    DEMO_MODEL,
    DEMO_RESPONSE,
    DEMO_TASK,
    DemoProvider,
    demo_settings,
    demo_workspace,
)
from agentproof.verifier import parse_report_text
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """Return a Click test runner."""
    return CliRunner()


def test_demo_workspace_writes_every_file() -> None:
    """The demo workspace contains every declared file."""
    with demo_workspace() as workspace:
        assert workspace.is_dir()
        for name in DEMO_FILES:
            assert (workspace / name).is_file()
        assert (workspace / "deploy.sh").stat().st_mode & 0o111


def test_demo_workspace_is_removed_afterwards() -> None:
    """The temporary demo workspace does not survive the context manager."""
    with demo_workspace() as workspace:
        captured = workspace
    assert not captured.exists()


def test_demo_settings_point_at_the_workspace() -> None:
    """The demo settings carry the demo task, claim, and auditor."""
    with demo_workspace() as workspace:
        settings = demo_settings(workspace)
    assert settings.task == DEMO_TASK
    assert settings.claim == DEMO_CLAIM
    assert settings.provider == "demo"
    assert settings.effective_model == DEMO_MODEL


def test_demo_provider_returns_a_parseable_payload() -> None:
    """The canned auditor answer parses into a report payload."""
    provider = DemoProvider()
    response = provider.complete(system="system", user="user")
    assert response.provider == "demo"
    assert response.model == DEMO_MODEL
    payload = parse_report_text(response.text)
    assert payload["verdict"] == DEMO_RESPONSE["verdict"]
    assert payload["checks"]


def test_demo_provider_reports_token_usage() -> None:
    """The demo provider reports a plausible token usage."""
    response = DemoProvider().complete(system="system", user="user")
    assert response.usage.prompt_tokens > 0
    assert response.usage.completion_tokens > 0


def test_demo_cli_runs_without_credentials(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--demo`` produces a report without any API key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(main, ["--demo"])
    assert result.exit_code == EXIT_FAILED
    assert "FAILED" in result.output
    assert "Evidence breakdown" in result.output


def test_demo_cli_downgrades_an_overconfident_verdict(runner: CliRunner) -> None:
    """The guard rails turn the demo's SUCCESS into a FAILED verdict."""
    result = runner.invoke(main, ["--demo"])
    assert "Downgraded to FAILED" in result.output


def test_demo_cli_json_output(runner: CliRunner) -> None:
    """``--demo --json`` emits a machine-readable report."""
    result = runner.invoke(main, ["--demo", "--json"])
    payload = json.loads(result.output)
    assert payload["verdict"] == "failed"
    assert payload["provider"] == "demo"
    assert payload["model"] == DEMO_MODEL
    assert payload["artifacts_scanned"] == len(DEMO_FILES)


def test_demo_cli_quiet_output(runner: CliRunner) -> None:
    """``--demo --quiet`` prints only the verdict line."""
    result = runner.invoke(main, ["--demo", "--quiet"])
    assert "FAILED" in result.output
    assert "Evidence breakdown" not in result.output


def test_demo_does_not_read_the_current_directory(runner: CliRunner, tmp_path: Path) -> None:
    """The demo ignores the working directory entirely."""
    (tmp_path / "secret.txt").write_text("do not read me\n", encoding="utf-8")
    result = runner.invoke(main, ["--demo"])
    assert result.exit_code == EXIT_FAILED
    assert "secret.txt" not in result.output
