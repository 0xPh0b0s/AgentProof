"""Tests for artifact collection."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentproof.artifacts import CollectorOptions, collect_artifacts
from agentproof.errors import WorkspaceError


def test_collects_text_files(workspace: Path) -> None:
    """Text files are collected with their content."""
    result = collect_artifacts(workspace)

    paths = {artifact.path for artifact in result.files}
    assert "deploy.sh" in paths
    assert "notes.md" in paths

    deploy = next(item for item in result.files if item.path == "deploy.sh")
    assert deploy.kind == "text"
    assert deploy.readable is True
    assert "echo deploying" in (deploy.content or "")


def test_detects_binary_and_empty_files(workspace: Path) -> None:
    """Binary and empty files are labelled correctly."""
    result = collect_artifacts(workspace)

    empty = next(item for item in result.files if item.path == "empty.txt")
    assert empty.kind == "empty"
    assert empty.content == ""

    binary = next(item for item in result.files if item.path.endswith("cache.bin"))
    assert binary.kind == "binary"
    assert binary.content is None


def test_respects_gitignore(workspace: Path) -> None:
    """Files matched by .gitignore are not collected."""
    (workspace / ".gitignore").write_text("notes.md\n", encoding="utf-8")

    result = collect_artifacts(workspace)

    paths = {artifact.path for artifact in result.files}
    assert "notes.md" not in paths
    assert "deploy.sh" in paths


def test_respects_explicit_excludes(workspace: Path) -> None:
    """Explicit exclude globs veto files from the collection."""
    options = CollectorOptions(exclude=["*.log"])

    result = collect_artifacts(workspace, options=options)

    paths = {artifact.path for artifact in result.files}
    assert "run.log" not in paths
    assert "deploy.sh" in paths


def test_respects_include_patterns(workspace: Path) -> None:
    """Include globs restrict the collection to matching files."""
    options = CollectorOptions(include=["*.md"])

    result = collect_artifacts(workspace, options=options)

    paths = {artifact.path for artifact in result.files}
    assert paths == {"notes.md"}


def test_enforces_file_limit(workspace: Path) -> None:
    """The collector stops once the file limit is reached."""
    options = CollectorOptions(max_files=2)

    result = collect_artifacts(workspace, options=options)

    assert result.count == 2
    assert result.budget_exhausted is True


def test_truncates_large_files(tmp_path: Path) -> None:
    """Files larger than the per-file limit are truncated."""
    root = tmp_path / "big"
    root.mkdir()
    (root / "large.txt").write_text("x" * 500, encoding="utf-8")

    options = CollectorOptions(max_file_bytes=100)
    result = collect_artifacts(root, options=options)

    artifact = result.files[0]
    assert artifact.truncated is True
    assert artifact.content is not None
    assert len(artifact.content) == 100


def test_missing_workspace_raises(tmp_path: Path) -> None:
    """A missing workspace is reported clearly."""
    with pytest.raises(WorkspaceError):
        collect_artifacts(tmp_path / "nope")


def test_single_file_workspace(tmp_path: Path) -> None:
    """A single file can be audited directly."""
    target = tmp_path / "output.txt"
    target.write_text("done", encoding="utf-8")

    result = collect_artifacts(target)

    assert result.count == 1
    assert result.files[0].content == "done"


def test_extra_paths_are_collected(tmp_path: Path) -> None:
    """Explicitly requested artifacts are added to the collection."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    extra = tmp_path / "extra.log"
    extra.write_text("log line", encoding="utf-8")

    result = collect_artifacts(workspace, extra_paths=[extra])

    assert result.count == 2
    assert "extra.log" in {artifact.path for artifact in result.files}


def test_summary_line(workspace: Path) -> None:
    """The summary line reports the collection size."""
    result = collect_artifacts(workspace)
    summary = result.summary_line()
    assert "files" in summary
    assert "B" in summary


def test_large_binary_does_not_starve_textual_evidence(tmp_path: Path) -> None:
    """A big binary is charged only for the inspected sample."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.bin").write_bytes(b"\x00" * 2_000_000)
    (workspace / "z_evidence.py").write_text("print('work')\n", encoding="utf-8")

    result = collect_artifacts(
        workspace,
        options=CollectorOptions(max_total_bytes=1_500_000, use_gitignore=False),
    )

    assert [artifact.path for artifact in result.files] == ["a.bin", "z_evidence.py"]
    assert result.budget_exhausted is False


def test_binaries_do_not_spend_the_text_budget(tmp_path: Path) -> None:
    """A binary encountered first cannot exhaust the budget for later text."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.bin").write_bytes(b"\x00" * 10_000)
    (workspace / "z.txt").write_text("evidence", encoding="utf-8")

    result = collect_artifacts(
        workspace,
        options=CollectorOptions(max_total_bytes=100, use_gitignore=False),
    )

    assert "z.txt" in {artifact.path for artifact in result.files}
    assert result.budget_exhausted is False


def test_prunes_ignored_directories(tmp_path: Path) -> None:
    """Ignored directories are not walked, so their files are never listed."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".gitignore").write_text("build/\n", encoding="utf-8")
    (workspace / "build").mkdir()
    (workspace / "build" / "out.js").write_text("bundle", encoding="utf-8")
    (workspace / "app.js").write_text("app", encoding="utf-8")

    result = collect_artifacts(workspace)

    assert {artifact.path for artifact in result.files} == {".gitignore", "app.js"}
    assert not any(path.startswith("build/") for path in result.skipped)


def test_nested_gitignore_rules_are_scoped_to_their_directory(tmp_path: Path) -> None:
    """A nested .gitignore applies below its directory, and nowhere else."""
    workspace = tmp_path / "ws"
    (workspace / "a" / "deep").mkdir(parents=True)
    (workspace / "b").mkdir()
    (workspace / "a" / ".gitignore").write_text("*.tmp\n", encoding="utf-8")
    (workspace / "a" / "drop.tmp").write_text("x", encoding="utf-8")
    (workspace / "a" / "deep" / "drop.tmp").write_text("x", encoding="utf-8")
    (workspace / "a" / "keep.txt").write_text("x", encoding="utf-8")
    (workspace / "b" / "drop.tmp").write_text("x", encoding="utf-8")

    result = collect_artifacts(workspace)

    paths = {artifact.path for artifact in result.files}
    assert "a/drop.tmp" not in paths
    assert "a/deep/drop.tmp" not in paths
    assert "a/keep.txt" in paths
    assert "b/drop.tmp" in paths


def test_reads_only_up_to_the_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The collector never reads a whole file just to truncate it."""
    target = tmp_path / "big.txt"
    target.write_text("x" * 1000, encoding="utf-8")

    def fail(_path: Path) -> bytes:
        raise AssertionError("the whole file was read")

    monkeypatch.setattr(Path, "read_bytes", fail)
    result = collect_artifacts(target, options=CollectorOptions(max_file_bytes=100))

    assert len(result.files[0].content or "") == 100
