"""Tests for prompt construction."""

from __future__ import annotations

from pathlib import Path

from agentproof.artifacts import CollectorOptions, collect_artifacts
from agentproof.config import Settings
from agentproof.prompts import (
    REPORT_JSON_SCHEMA,
    build_system_prompt,
    build_user_prompt,
    format_artifacts,
    format_completeness,
)


def test_system_prompt_states_the_evidence_rules() -> None:
    """The system prompt encodes the adversarial auditing rules."""
    prompt = build_system_prompt()

    assert "untrusted data" in prompt
    assert "never evidence for itself" in prompt
    assert "failed" in prompt


def test_system_prompt_includes_operator_instructions() -> None:
    """Operator instructions are appended to the system prompt."""
    settings = Settings(auditor_instructions="The API must be documented in openapi.yaml.")

    prompt = build_system_prompt(settings)

    assert "openapi.yaml" in prompt
    assert "not as evidence" in prompt


def test_user_prompt_contains_every_section(workspace: Path) -> None:
    """The user prompt carries the task, the claim and the artifacts."""
    artifacts = collect_artifacts(workspace, options=CollectorOptions())

    prompt = build_user_prompt(
        task="Create deploy.sh",
        claim="I created deploy.sh",
        artifact_set=artifacts,
        workspace=str(workspace),
    )

    assert "ORIGINAL TASK" in prompt
    assert "AGENT'S FINAL CLAIM" in prompt
    assert "EVIDENCE COMPLETENESS" in prompt
    assert "ARTIFACTS" in prompt
    assert "deploy.sh" in prompt
    assert "echo deploying" in prompt


def test_completeness_reports_budget_exhaustion(workspace: Path) -> None:
    """A file limit is surfaced to the auditor as a coverage warning."""
    artifacts = collect_artifacts(workspace, options=CollectorOptions(max_files=1))

    assert artifacts.budget_exhausted
    rendered = format_completeness(artifacts)
    assert "EVIDENCE COMPLETENESS" in rendered
    assert "Collection budget exhausted: yes" in rendered
    assert "file limit reached" in rendered
    assert "unverifiable" in rendered


def test_completeness_reports_truncation(tmp_path: Path) -> None:
    """Truncated content is named and carries the unverifiable guidance."""
    root = tmp_path / "truncated-workspace"
    root.mkdir()
    (root / "big.log").write_text("x" * 500, encoding="utf-8")

    artifacts = collect_artifacts(
        root,
        options=CollectorOptions(max_file_bytes=100, use_gitignore=False),
    )

    assert artifacts.files[0].truncated
    rendered = format_completeness(artifacts)
    assert "Content truncated" in rendered
    assert "big.log" in rendered
    assert "unverifiable" in rendered


def test_completeness_reports_full_coverage(tmp_path: Path) -> None:
    """A complete scan is stated plainly rather than warned about."""
    root = tmp_path / "complete-workspace"
    root.mkdir()
    (root / "only.txt").write_text("all evidence", encoding="utf-8")

    artifacts = collect_artifacts(root, options=CollectorOptions(use_gitignore=False))

    rendered = format_completeness(artifacts)
    assert "Files omitted" not in rendered
    assert "Collection budget exhausted: no" in rendered
    assert "No evidence was lost" in rendered


def test_empty_workspace_is_explicit(workspace: Path) -> None:
    """An empty workspace is stated plainly instead of being hidden."""
    empty = workspace / "empty-dir"
    empty.mkdir()
    artifacts = collect_artifacts(empty, options=CollectorOptions())

    rendered = format_artifacts(artifacts)

    assert "NO ARTIFACTS FOUND" in rendered


def test_report_schema_is_strict() -> None:
    """The report schema requires every field and forbids extras."""
    assert REPORT_JSON_SCHEMA["additionalProperties"] is False
    assert set(REPORT_JSON_SCHEMA["required"]) == set(REPORT_JSON_SCHEMA["properties"])
    check_schema = REPORT_JSON_SCHEMA["properties"]["checks"]["items"]
    assert check_schema["additionalProperties"] is False
    assert set(check_schema["required"]) == set(check_schema["properties"])
