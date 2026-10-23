"""Tests for the command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentproof.cli import EXIT_FAILED, EXIT_PROVIDER, EXIT_SUCCESS, EXIT_USAGE, main
from agentproof.errors import ProviderError
from agentproof.providers.base import LLMResponse
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """Return a Click test runner."""
    return CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a project directory with a workspace and configuration."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "deploy.sh").write_text("#!/bin/sh\necho deploying\n", encoding="utf-8")
    (tmp_path / ".agentproof.json").write_text(
        json.dumps(
            {
                "task": "Create a deployment script.",
                "claim": "I created deploy.sh.",
                "workspace": "./workspace",
                "provider": "anthropic",
                "model": "claude-sonnet-5-5",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _install_fake_provider(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    """Replace the provider factory with a stub returning ``payload``.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        payload: The JSON payload the fake auditor should return.
    """

    class FakeProvider:
        """A provider stub returning a canned response."""

        spec = type("Spec", (), {"name": "fake", "label": "Fake", "env_var": "FAKE_KEY"})()

        def complete(self, **kwargs: object) -> LLMResponse:
            """Return the canned response."""
            return LLMResponse(
                text=json.dumps(payload),
                model="fake-model",
                provider="fake",
            )

        def close(self) -> None:
            """No resources to release."""

    def fake_create_provider(**kwargs: object) -> FakeProvider:
        return FakeProvider()

    monkeypatch.setattr("agentproof.cli.create_provider", fake_create_provider)


_SUCCESS_PAYLOAD = {
    "verdict": "success",
    "confidence": 0.95,
    "summary": "The script exists.",
    "checks": [
        {
            "requirement": "Create deploy.sh",
            "status": "verified",
            "evidence": "deploy.sh present",
            "source": "deploy.sh",
        }
    ],
    "discrepancies": [],
    "hallucinations": [],
    "missing_items": [],
    "recommendations": [],
    "notes": "",
}

_FAILED_PAYLOAD = {
    "verdict": "failed",
    "confidence": 0.9,
    "summary": "Nothing was produced.",
    "checks": [
        {
            "requirement": "Create deploy.sh",
            "status": "missing",
            "evidence": "not found",
            "source": "",
        }
    ],
    "discrepancies": [],
    "hallucinations": [],
    "missing_items": ["deploy.sh"],
    "recommendations": [],
    "notes": "",
}


def test_check_reports_success(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful audit exits with code 0 and shows the badge."""
    _install_fake_provider(monkeypatch, _SUCCESS_PAYLOAD)

    result = runner.invoke(main, ["--check", "--no-color"])

    assert result.exit_code == EXIT_SUCCESS
    assert "SUCCESS" in result.output
    assert "deploy.sh" in result.output


def test_check_reports_failure(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed audit exits with code 1."""
    _install_fake_provider(monkeypatch, _FAILED_PAYLOAD)

    result = runner.invoke(main, ["--check", "--no-color"])

    assert result.exit_code == EXIT_FAILED
    assert "FAILED" in result.output


def test_check_json_output(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The JSON output mode emits a parseable report."""
    _install_fake_provider(monkeypatch, _SUCCESS_PAYLOAD)

    result = runner.invoke(main, ["--check", "--json"])

    assert result.exit_code == EXIT_SUCCESS
    payload = json.loads(result.output)
    assert payload["verdict"] == "success"
    assert payload["checks"][0]["status"] == "verified"


def test_quiet_mode(runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The quiet mode prints only the verdict line."""
    _install_fake_provider(monkeypatch, _SUCCESS_PAYLOAD)

    result = runner.invoke(main, ["--check", "--quiet", "--no-color"])

    assert result.exit_code == EXIT_SUCCESS
    assert "SUCCESS" in result.output
    assert "Evidence breakdown" not in result.output


def test_quiet_mode_does_not_leak_rich_markup(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The quiet mode renders the badge instead of printing its markup."""
    _install_fake_provider(monkeypatch, _SUCCESS_PAYLOAD)

    result = runner.invoke(main, ["--check", "--quiet", "--no-color"])

    assert "[bold" not in result.output
    assert "[/bold" not in result.output


def test_dry_run_does_not_call_the_api(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dry run prints the prompt and never contacts the provider."""

    def fail(**kwargs: object) -> None:
        raise AssertionError("the provider must not be called during a dry run")

    monkeypatch.setattr("agentproof.cli.create_provider", fail)

    result = runner.invoke(main, ["--check", "--dry-run", "--no-color"])

    assert result.exit_code == EXIT_SUCCESS
    assert "System prompt" in result.output
    assert "ORIGINAL TASK" in result.output


def test_missing_credentials_are_reported(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing API key produces an actionable error."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = runner.invoke(main, ["--check", "--no-color"])

    assert result.exit_code == EXIT_USAGE
    assert "ANTHROPIC_API_KEY" in result.output


def test_provider_failure_is_reported(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider failure exits with the provider exit code."""

    def failing_create_provider(**kwargs: object) -> object:
        class Failing:
            """A provider that always fails."""

            spec = type("Spec", (), {"name": "fake"})()

            def complete(self, **kwargs: object) -> LLMResponse:
                raise ProviderError("upstream exploded", provider="fake", status_code=500)

            def close(self) -> None:
                """No resources to release."""

        return Failing()

    monkeypatch.setattr("agentproof.cli.create_provider", failing_create_provider)

    result = runner.invoke(main, ["--check", "--no-color"])

    assert result.exit_code == EXIT_PROVIDER
    assert "upstream exploded" in result.output


def test_missing_task_is_reported(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing task definition produces an actionable error."""
    (tmp_path / ".agentproof.json").write_text(
        json.dumps({"claim": "I did it", "workspace": "."}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(main, ["--check", "--no-color"])

    assert result.exit_code == EXIT_USAGE
    assert "task" in result.output.lower()


def test_doctor_reports_missing_configuration(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The doctor command reports missing configuration."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(main, ["doctor", "--no-color"])

    assert result.exit_code == EXIT_USAGE
    assert "Problems found" in result.output


def test_doctor_reports_healthy_configuration(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The doctor command reports a healthy setup."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key-1234")

    result = runner.invoke(main, ["doctor", "--no-color"])

    assert result.exit_code == EXIT_SUCCESS
    assert "Everything looks good" in result.output


def test_cli_overrides_the_config_file(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Command-line values take precedence over the configuration file."""
    captured: dict[str, object] = {}

    def fake_create_provider(**kwargs: object) -> object:
        captured.update(kwargs)

        class Failing:
            """A provider that fails after capturing its arguments."""

            spec = type("Spec", (), {"name": "fake"})()

            def complete(self, **kwargs: object) -> LLMResponse:
                raise ProviderError("stop", provider="fake")

            def close(self) -> None:
                """No resources to release."""

        return Failing()

    monkeypatch.setattr("agentproof.cli.create_provider", fake_create_provider)

    result = runner.invoke(
        main,
        ["--check", "--model", "custom-model", "--min-confidence", "0.9", "--no-color"],
    )

    assert result.exit_code == EXIT_PROVIDER
    assert captured["model"] == "custom-model"


def test_init_writes_a_configuration_file(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wizard writes a usable configuration file."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        main,
        ["init", "--no-color"],
        input="Ship the feature\n\nI shipped it\n\n./ws\n\nanthropic\nclaude-sonnet-5-5\n0.75\nn\n",
    )

    assert result.exit_code == EXIT_SUCCESS, result.output
    config = json.loads((tmp_path / ".agentproof.json").read_text(encoding="utf-8"))
    assert config["task"] == "Ship the feature"
    assert config["claim"] == "I shipped it"
    assert config["provider"] == "anthropic"
    assert config["model"] == "claude-sonnet-5-5"


def test_version_option(runner: CliRunner) -> None:
    """The version option prints the package version."""
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == EXIT_SUCCESS
    assert "agentproof" in result.output


def test_help_lists_the_check_flag(runner: CliRunner) -> None:
    """The help text advertises the --check workflow."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == EXIT_SUCCESS
    assert "--check" in result.output
    assert "doctor" in result.output
    assert "init" in result.output
