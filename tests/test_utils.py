"""Tests for the glob and ignore-matching helpers."""

from __future__ import annotations

import pytest
from agentproof.utils import (
    IgnoreRule,
    PathMatcher,
    compile_glob,
    extract_json_object,
    human_bytes,
    looks_binary,
)


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("*.pyc", "main.pyc", True),
        ("*.pyc", "src/main.pyc", False),
        ("*.pyc", "main.py", False),
        ("src/**", "src/a/b/c.py", True),
        ("src/**", "other/a.py", False),
        ("?.txt", "a.txt", True),
        ("?.txt", "ab.txt", False),
        ("[ab].txt", "a.txt", True),
        ("[ab].txt", "c.txt", False),
        ("build", "build", True),
        ("build", "build/x.o", False),
    ],
)
def test_compile_glob(pattern: str, path: str, expected: bool) -> None:
    """Glob translation handles the common cases."""
    assert bool(compile_glob(pattern).match(path)) is expected


def test_compile_glob_any_depth() -> None:
    """A pattern without a separator can be matched at any depth."""
    pattern = compile_glob("*.log", any_depth=True)

    assert pattern.match("app.log") is not None
    assert pattern.match("logs/app.log") is not None
    assert pattern.match("app.txt") is None


def test_compile_glob_any_depth_keeps_paths_anchored() -> None:
    """A pattern containing a separator stays anchored."""
    pattern = compile_glob("src/*.py", any_depth=True)

    assert pattern.match("src/app.py") is not None
    assert pattern.match("lib/src/app.py") is None


def test_ignore_rule_directory_only() -> None:
    """A trailing slash restricts a rule to directories."""
    rule = IgnoreRule.parse("node_modules/")
    assert rule is not None
    assert rule.directory_only is True
    assert rule.matches("node_modules", is_dir=True) is True
    assert rule.matches("node_modules", is_dir=False) is False


def test_matcher_ignores_files_inside_an_ignored_directory() -> None:
    """Files below an ignored directory are ignored as well."""
    rules = [rule for rule in (IgnoreRule.parse("node_modules/"),) if rule]
    matcher = PathMatcher(rules)

    assert matcher.is_ignored("node_modules", is_dir=True) is True
    assert matcher.is_ignored("node_modules/pkg/index.js") is True
    assert matcher.is_ignored("src/node_modules/pkg/index.js") is True
    assert matcher.is_ignored("src/app.py") is False


def test_ignore_rule_negation() -> None:
    """A leading bang re-includes a path."""
    rule = IgnoreRule.parse("!keep.log")
    assert rule is not None
    assert rule.negated is True


def test_ignore_rule_comments_and_blanks() -> None:
    """Comments and blank lines are ignored."""
    assert IgnoreRule.parse("# comment") is None
    assert IgnoreRule.parse("   ") is None


def test_path_matcher_applies_rules_in_order() -> None:
    """Later rules win over earlier ones."""
    rules = [rule for rule in (IgnoreRule.parse("*.log"), IgnoreRule.parse("!keep.log")) if rule]
    matcher = PathMatcher(rules)
    assert matcher.is_ignored("debug.log") is True
    assert matcher.is_ignored("keep.log") is False


def test_path_matcher_include_and_exclude() -> None:
    """Include and exclude globs are honoured."""
    matcher = PathMatcher(includes=["src/**"], excludes=["src/secret.txt"])
    assert matcher.is_included("src/app.py") is True
    assert matcher.is_included("docs/readme.md") is False
    assert matcher.is_excluded("src/secret.txt") is True
    assert matcher.is_excluded("src/app.py") is False


def test_path_matcher_without_includes_accepts_everything() -> None:
    """An empty include list does not filter anything."""
    matcher = PathMatcher()
    assert matcher.is_included("anything/at/all.txt") is True


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('prefix {"a": {"b": 2}} suffix', '{"a": {"b": 2}}'),
        ('{"a": "}"}', '{"a": "}"}'),
        ('{"a": "escaped \\" quote"}', '{"a": "escaped \\" quote"}'),
        ("no json here", None),
    ],
)
def test_extract_json_object(text: str, expected: str | None) -> None:
    """JSON extraction finds the first balanced object."""
    assert extract_json_object(text) == expected


@pytest.mark.parametrize(
    ("size", "expected"),
    [(0, "0 B"), (512, "512 B"), (2048, "2.0 KB"), (5 * 1024 * 1024, "5.0 MB")],
)
def test_human_bytes(size: int, expected: str) -> None:
    """Byte counts are formatted with human-readable units."""
    assert human_bytes(size) == expected


def test_looks_binary() -> None:
    """Binary content is detected by null bytes."""
    assert looks_binary(b"\x00\x01\x02") is True
    assert looks_binary(b"plain text content\n") is False
    assert looks_binary(b"") is False
