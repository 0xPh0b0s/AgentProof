"""Discovery and collection of the artifacts an agent produced.

The collector walks a workspace directory, honours ``.gitignore`` files and
explicit include/exclude globs, and reads the textual content of every
relevant file so that an auditor model can inspect the actual evidence rather
than a directory listing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from agentproof.utils import IgnoreRule, PathMatcher, human_bytes, looks_binary, relative_to

__all__ = [
    "Artifact",
    "ArtifactSet",
    "CollectorOptions",
    "collect_artifacts",
    "load_gitignore_rules",
]


#: Directories and files that are never useful as evidence and are excluded by
#: default. The list is deliberately small: anything an agent plausibly
#: produced (including ``dist`` or ``build`` output) stays visible.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git/",
    ".hg/",
    ".svn/",
    ".venv/",
    "venv/",
    "env/",
    "node_modules/",
    "__pycache__/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".tox/",
    ".ipynb_checkpoints/",
    ".idea/",
    ".vscode/",
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".env",
    ".env.*",
)


@dataclass(frozen=True, slots=True)
class Artifact:
    """A single file considered as evidence.

    Attributes:
        path: Path relative to the workspace root.
        absolute_path: Absolute path on disk.
        size: Size of the file in bytes.
        modified: Modification time as a POSIX timestamp.
        kind: One of ``"text"``, ``"binary"`` or ``"empty"``.
        content: Decoded text content, when the file is textual.
        truncated: Whether the content was cut short by the size limit.
    """

    path: str
    absolute_path: Path
    size: int
    modified: float
    kind: str
    content: str | None = None
    truncated: bool = False

    @property
    def readable(self) -> bool:
        """Whether the artifact carries inspectable text."""
        return self.kind == "text" and self.content is not None


@dataclass(slots=True)
class ArtifactSet:
    """The result of scanning a workspace.

    Attributes:
        root: The workspace root that was scanned.
        files: Artifacts selected for the audit.
        skipped: Mapping of path to the reason it was skipped.
        total_bytes: Total size of the selected artifacts.
        budget_exhausted: Whether a limit stopped the scan early.
        roots: Every path that was scanned (workspace plus explicit artifacts).
    """

    root: Path
    files: list[Artifact] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    total_bytes: int = 0
    budget_exhausted: bool = False
    roots: list[Path] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Number of artifacts collected."""
        return len(self.files)

    def summary_line(self) -> str:
        """Return a one-line human summary of the collected artifacts."""
        binary = sum(1 for item in self.files if item.kind == "binary")
        truncated = sum(1 for item in self.files if item.truncated)
        parts = [
            f"{self.count} file{'s' if self.count != 1 else ''}",
            human_bytes(self.total_bytes),
        ]
        if binary:
            parts.append(f"{binary} binary")
        if truncated:
            parts.append(f"{truncated} truncated")
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped")
        return ", ".join(parts)


@dataclass(slots=True)
class CollectorOptions:
    """Tuning knobs for :func:`collect_artifacts`.

    Attributes:
        max_files: Maximum number of artifacts to collect.
        max_file_bytes: Maximum number of bytes read from a single file.
        max_total_bytes: Maximum number of bytes read across all files.
        include: Glob patterns restricting which files are collected.
        exclude: Glob patterns vetoing files from the collection.
        use_gitignore: Whether ``.gitignore`` files are honoured.
        follow_symlinks: Whether symlinked files are followed.
    """

    max_files: int = 200
    max_file_bytes: int = 120_000
    max_total_bytes: int = 1_500_000
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    use_gitignore: bool = True
    follow_symlinks: bool = False


def _parse_gitignore(path: Path, base: str) -> list[IgnoreRule]:
    """Parse a ``.gitignore`` file into rules anchored at ``base``."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    rules: list[IgnoreRule] = []
    for line in lines:
        rule = IgnoreRule.parse(line, base=base)
        if rule is not None:
            rules.append(rule)
    return rules


def load_gitignore_rules(root: Path, matcher_excludes: list[str]) -> list[IgnoreRule]:
    """Collect the default excludes, explicit excludes, and root ignore rules.

    Args:
        root: The workspace root.
        matcher_excludes: Additional user-supplied exclude patterns, treated
            as directory-style rules.

    Returns:
        The ordered list of ignore rules that apply inside the workspace.
    """
    rules: list[IgnoreRule] = []
    for pattern in [*DEFAULT_EXCLUDES, *matcher_excludes]:
        rule = IgnoreRule.parse(pattern)
        if rule is not None:
            rules.append(rule)

    rules.extend(_parse_gitignore(root / ".gitignore", ""))
    return rules


def _read_text(path: Path, limit: int) -> tuple[str | None, bool, bool]:
    """Read a file as text.

    Args:
        path: File to read.
        limit: Maximum number of bytes to read.

    Returns:
        A tuple of ``(content, truncated, is_binary)``. ``content`` is
        ``None`` for binary files.
    """
    try:
        with path.open("rb") as handle:
            # One extra byte is enough to detect truncation without reading
            # a potentially huge file to the end.
            raw = handle.read(limit + 1)
    except OSError:
        return None, False, False

    if not raw:
        return "", False, False

    truncated = len(raw) > limit
    sample = raw[:limit]
    if looks_binary(sample):
        return None, truncated, True

    try:
        return sample.decode("utf-8"), truncated, False
    except UnicodeDecodeError:
        return sample.decode("utf-8", errors="replace"), truncated, False


def _iter_files(
    directory: Path,
    matcher: PathMatcher,
    *,
    use_gitignore: bool,
    follow_symlinks: bool,
) -> list[Path]:
    """Return every non-ignored file under ``directory``.

    Ignored directories are pruned during the walk, and nested ``.gitignore``
    files are loaded as their directory is reached so their rules apply to the
    subtree below them.

    Args:
        directory: Directory to walk.
        matcher: Matcher carrying the ignore rules.
        use_gitignore: Whether nested ``.gitignore`` files are honoured.
        follow_symlinks: Whether symlinked directories are descended into.

    Returns:
        A sorted list of file paths.
    """
    collected: list[Path] = []
    for current, dirnames, filenames in os.walk(directory, followlinks=follow_symlinks):
        current_path = Path(current)
        if use_gitignore and current_path != directory and ".gitignore" in filenames:
            base = relative_to(current_path, directory)
            matcher.rules.extend(_parse_gitignore(current_path / ".gitignore", base))

        kept: list[str] = []
        for name in sorted(dirnames):
            path = current_path / name
            if not follow_symlinks and path.is_symlink():
                continue
            if matcher.is_ignored(relative_to(path, directory), is_dir=True):
                continue
            kept.append(name)
        dirnames[:] = kept

        for name in sorted(filenames):
            path = current_path / name
            if not matcher.is_ignored(relative_to(path, directory), is_dir=False):
                collected.append(path)
    return collected


def collect_artifacts(
    workspace: Path,
    *,
    extra_paths: list[Path] | None = None,
    options: CollectorOptions | None = None,
) -> ArtifactSet:
    """Collect the artifacts that should be presented to the auditor.

    Args:
        workspace: The agent's workspace directory (or a single file).
        extra_paths: Additional explicit files or directories to include.
        options: Collector tuning knobs.

    Returns:
        The populated :class:`ArtifactSet`.

    Raises:
        WorkspaceError: If the workspace does not exist.
    """
    from agentproof.errors import WorkspaceError

    opts = options or CollectorOptions()
    workspace = workspace.expanduser()

    if not workspace.exists():
        raise WorkspaceError(f"Workspace path does not exist: {workspace}")

    roots: list[Path] = [workspace]
    if extra_paths:
        roots.extend(path.expanduser() for path in extra_paths)

    result = ArtifactSet(root=workspace, roots=roots)
    seen: set[Path] = set()

    for root in roots:
        if not root.exists():
            result.skipped[root.as_posix()] = "path does not exist"
            continue

        if root.is_file():
            candidates = [root]
            matcher = PathMatcher(includes=opts.include, excludes=opts.exclude)
            base = root.parent
        else:
            base = root
            rules = load_gitignore_rules(root, opts.exclude) if opts.use_gitignore else []
            matcher = PathMatcher(rules, includes=opts.include, excludes=opts.exclude)
            candidates = _iter_files(
                root,
                matcher,
                use_gitignore=opts.use_gitignore,
                follow_symlinks=opts.follow_symlinks,
            )

        for path in candidates:
            resolved = path.resolve()
            if resolved in seen:
                continue

            rel = relative_to(path, base)
            if matcher.is_excluded(rel):
                result.skipped[rel] = "excluded by pattern"
                continue
            if not matcher.is_included(rel):
                result.skipped[rel] = "not matched by include patterns"
                continue
            if not opts.follow_symlinks and path.is_symlink():
                result.skipped[rel] = "symlink"
                continue

            try:
                stat = path.stat()
            except OSError as exc:
                result.skipped[rel] = f"unreadable ({exc.strerror})"
                continue

            if result.count >= opts.max_files:
                result.budget_exhausted = True
                result.skipped[rel] = "file limit reached"
                continue

            remaining = opts.max_total_bytes - result.total_bytes
            if remaining <= 0:
                result.budget_exhausted = True
                result.skipped[rel] = "total size budget exhausted"
                continue

            read_limit = min(opts.max_file_bytes, remaining)
            content, truncated, is_binary = _read_text(path, read_limit)
            if content is not None:
                result.total_bytes += len(content.encode("utf-8", errors="replace"))
            # Binary content is never shown to the auditor, so it does not
            # spend the text budget; a large blob cannot crowd out readable
            # evidence that appears later in the walk.

            if is_binary:
                kind = "binary"
                text = None
            elif not content:
                kind = "empty"
                text = ""
            else:
                kind = "text"
                text = content

            seen.add(resolved)
            result.files.append(
                Artifact(
                    path=rel,
                    absolute_path=path,
                    size=stat.st_size,
                    modified=stat.st_mtime,
                    kind=kind,
                    content=text,
                    truncated=truncated,
                )
            )

    return result
