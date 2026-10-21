"""Assembly of the verification context.

The context bundles everything the auditor needs: the original task, the
agent's claim, and the artifacts found in the workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentproof.artifacts import ArtifactSet, CollectorOptions, collect_artifacts
from agentproof.config import Settings
from agentproof.errors import ConfigurationError, WorkspaceError

__all__ = ["VerificationContext", "build_context", "collector_options"]


@dataclass(slots=True)
class VerificationContext:
    """Everything the verification engine needs to audit a claim.

    Attributes:
        task: The original task definition.
        claim: The agent's claim of what it accomplished.
        workspace: The workspace that was inspected.
        artifact_set: The artifacts gathered from the workspace.
    """

    task: str
    claim: str
    workspace: Path
    artifact_set: ArtifactSet

    @property
    def artifact_count(self) -> int:
        """Number of artifacts available to the auditor."""
        return self.artifact_set.count


def collector_options(settings: Settings) -> CollectorOptions:
    """Translate settings into collector options.

    Args:
        settings: The resolved settings.

    Returns:
        The collector configuration.
    """
    return CollectorOptions(
        max_files=settings.max_files,
        max_file_bytes=settings.max_artifact_bytes,
        max_total_bytes=settings.max_total_bytes,
        include=list(settings.include),
        exclude=list(settings.exclude),
    )


def build_context(
    settings: Settings,
    *,
    task: str | None = None,
    claim: str | None = None,
    workspace: Path | None = None,
) -> VerificationContext:
    """Build the verification context for a run.

    Args:
        settings: The resolved settings.
        task: Task definition overriding the configured one.
        claim: Claim overriding the configured one.
        workspace: Workspace overriding the configured one.

    Returns:
        The assembled context.

    Raises:
        ConfigurationError: If the task or the claim is missing.
        WorkspaceError: If the workspace cannot be read.
    """
    resolved_task = (task if task is not None else settings.task) or ""
    resolved_claim = (claim if claim is not None else settings.claim) or ""
    resolved_workspace = workspace or settings.workspace or Path.cwd()

    if not resolved_task.strip():
        raise ConfigurationError(
            "No task definition was provided. Set 'task' in .agentproof.json, "
            "export AGENTPROOF_TASK, or pass --task."
        )
    if not resolved_claim.strip():
        raise ConfigurationError(
            "No agent claim was provided. Set 'claim' in .agentproof.json, "
            "export AGENTPROOF_CLAIM, or pass --claim."
        )

    resolved_workspace = resolved_workspace.expanduser()
    if not resolved_workspace.exists():
        raise WorkspaceError(f"Workspace path does not exist: {resolved_workspace}")

    extra_paths: list[Path] = []
    for item in settings.artifacts:
        candidate = Path(item).expanduser()
        if not candidate.is_absolute():
            candidate = resolved_workspace / candidate
        extra_paths.append(candidate)

    artifact_set = collect_artifacts(
        resolved_workspace,
        extra_paths=extra_paths,
        options=collector_options(settings),
    )

    return VerificationContext(
        task=resolved_task.strip(),
        claim=resolved_claim.strip(),
        workspace=resolved_workspace,
        artifact_set=artifact_set,
    )
