"""Small, dependency-free helpers shared across AgentProof.

The helpers here implement the subset of ``.gitignore`` semantics AgentProof
needs in order to decide which workspace files are worth showing to an auditor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "IgnoreRule",
    "PathMatcher",
    "compile_glob",
    "extract_json_object",
    "human_bytes",
    "looks_binary",
]


def compile_glob(pattern: str, *, any_depth: bool = False) -> re.Pattern[str]:
    """Compile a glob pattern into a regular expression.

    Supports ``*`` (any run of characters within one path segment), ``**``
    (any number of path segments), ``?`` (a single character) and character
    classes such as ``[0-9]``.

    Args:
        pattern: Glob pattern to compile.
        any_depth: When ``True`` and the pattern contains no ``/``, the pattern
            also matches at any directory depth (gitignore-style behaviour).

    Returns:
        A compiled regular expression matching the pattern against a relative
        POSIX-style path.
    """
    i = 0
    n = len(pattern)
    out: list[str] = []
    while i < n:
        char = pattern[i]
        i += 1
        if char == "*":
            if i < n and pattern[i] == "*":
                i += 1
                if i < n and pattern[i] == "/":
                    i += 1
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                out.append(re.escape("["))
                continue
            body = pattern[i:end].replace("\\", "\\\\")
            i = end + 1
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append(f"[{body}]")
        else:
            out.append(re.escape(char))

    prefix = "(?:.*/)?" if any_depth and "/" not in pattern else ""
    return re.compile("^" + prefix + "".join(out) + "$")


@dataclass(frozen=True, slots=True)
class IgnoreRule:
    """A single ``.gitignore``-style rule.

    Attributes:
        pattern: The original pattern text.
        negated: ``True`` for ``!``-prefixed re-inclusion rules.
        directory_only: ``True`` when the pattern ends with ``/``.
        anchored: ``True`` when the pattern is relative to its base directory.
        regex: Compiled matcher for the path the rule names.
    """

    pattern: str
    negated: bool
    directory_only: bool
    anchored: bool
    regex: re.Pattern[str]

    @classmethod
    def parse(cls, raw: str, *, base: str = "") -> IgnoreRule | None:
        """Parse a single ``.gitignore`` line.

        Args:
            raw: The raw line from a ``.gitignore`` file.
            base: Path prefix of the directory containing the ``.gitignore``,
                used to anchor patterns.

        Returns:
            The parsed rule, or ``None`` for blank lines and comments.
        """
        line = raw.rstrip("\n").rstrip("\r")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return None

        negated = stripped.startswith("!")
        if negated:
            stripped = stripped[1:]

        directory_only = stripped.endswith("/")
        if directory_only:
            stripped = stripped[:-1]

        # Unescape a leading "\#" or "\!" per gitignore semantics.
        if stripped.startswith("\\"):
            stripped = stripped[1:]

        if not stripped:
            return None

        anchored = "/" in stripped
        if stripped.startswith("/"):
            stripped = stripped[1:]
            anchored = True

        prefix = f"{base}/" if base else ""
        body = compile_glob(stripped).pattern[1:-1]

        if anchored:
            regex = re.compile(rf"^{prefix}{body}$")
        elif prefix:
            # An unanchored rule in a nested .gitignore matches at any depth
            # below that directory, but not above it.
            regex = re.compile(rf"^{prefix}(?:.*/)?{body}$")
        else:
            regex = re.compile(rf"^(?:.*/)?{body}$")

        return cls(
            pattern=raw,
            negated=negated,
            directory_only=directory_only,
            anchored=anchored,
            regex=regex,
        )

    def matches(self, rel_path: str, *, is_dir: bool) -> bool:
        """Return ``True`` when the rule applies to the given path.

        Args:
            rel_path: Path relative to the rule's base directory.
            is_dir: Whether the path refers to a directory.
        """
        if self.directory_only and not is_dir:
            # A directory-only rule never names a file directly; it is applied
            # to the parent directories of a path by the matcher.
            return False
        return self.regex.match(rel_path) is not None


class PathMatcher:
    """Evaluate ignore rules and include/exclude globs against relative paths.

    Args:
        rules: Ordered ``.gitignore``-style rules; later rules win.
        includes: Glob patterns that, when present, restrict what is matched.
        excludes: Glob patterns that veto a match.
    """

    def __init__(
        self,
        rules: list[IgnoreRule] | None = None,
        *,
        includes: list[str] | None = None,
        excludes: list[str] | None = None,
    ) -> None:
        """Compile the ignore rules and the include/exclude globs."""
        self.rules = rules or []
        self._include_res = [compile_glob(pattern, any_depth=True) for pattern in (includes or [])]
        self._exclude_res = [compile_glob(pattern, any_depth=True) for pattern in (excludes or [])]

    def is_ignored(self, rel_path: str, *, is_dir: bool = False) -> bool:
        """Return ``True`` when the path is excluded by the ignore rules.

        Every ancestor directory of the path is tested as well, so a file
        inside an ignored directory is ignored too.

        Args:
            rel_path: Path relative to the workspace root.
            is_dir: Whether the path refers to a directory.

        Returns:
            ``True`` when the path should be skipped.
        """
        ignored = False
        parts = rel_path.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            prefix_is_dir = index < len(parts) or is_dir
            for rule in self.rules:
                if rule.matches(prefix, is_dir=prefix_is_dir):
                    ignored = not rule.negated
        return ignored

    def is_excluded(self, rel_path: str) -> bool:
        """Return ``True`` when the path is vetoed by an explicit exclude glob."""
        return any(regex.match(rel_path) for regex in self._exclude_res)

    def is_included(self, rel_path: str) -> bool:
        """Return ``True`` when the path passes the include globs.

        When no include globs are configured, every path is included.
        """
        if not self._include_res:
            return True
        return any(regex.match(rel_path) for regex in self._include_res)


def looks_binary(sample: bytes) -> bool:
    """Heuristically decide whether a byte sample comes from a binary file.

    Args:
        sample: The first bytes of the file.

    Returns:
        ``True`` when the sample looks like binary content.
    """
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    # A high proportion of non-printable bytes implies binary content.
    text_chars = bytes(range(32, 127)) + b"\n\r\t\f\b"
    non_text = sum(1 for byte in sample if byte not in text_chars)
    return non_text / len(sample) > 0.30


def human_bytes(size: int) -> str:
    """Format a byte count using human-friendly units.

    Args:
        size: Number of bytes.

    Returns:
        A short string such as ``"1.4 KB"``.
    """
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def extract_json_object(text: str) -> str | None:
    """Extract the first balanced JSON object from a text blob.

    LLMs sometimes wrap JSON in prose or Markdown fences; this helper finds the
    first ``{`` and returns the substring up to its matching ``}`` while
    respecting string literals and escapes.

    Args:
        text: Raw model output.

    Returns:
        The JSON object text, or ``None`` when no balanced object is present.
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        start = text.find("{", start + 1)
    return None


def relative_to(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` as a POSIX-style string.

    Args:
        path: The path to convert.
        root: The directory to make it relative to.

    Returns:
        A POSIX-style relative path, or the absolute path if it is not under
        ``root``.
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
