"""Tests for configuration discovery, merging and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentproof.config import (
    CONFIG_FILENAME,
    load_settings,
    read_config_file,
    save_config_file,
    user_config_path,
)
from agentproof.errors import ConfigurationError


def test_discovers_project_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A .agentproof.json in the working directory is discovered."""
    (tmp_path / CONFIG_FILENAME).write_text(
        json.dumps({"task": "Do the thing", "claim": "Did the thing"}),
        encoding="utf-8",
    )
    nested = tmp_path / "nested" / "deep"
    nested.mkdir(parents=True)

    settings = load_settings(cwd=nested, use_dotenv=False, use_env=False)

    assert settings.task == "Do the thing"
    assert settings.claim == "Did the thing"
    assert settings.config_path == tmp_path / CONFIG_FILENAME


def test_cli_overrides_beat_config_file(tmp_path: Path) -> None:
    """Explicit overrides win over the configuration file."""
    (tmp_path / CONFIG_FILENAME).write_text(
        json.dumps({"task": "from file", "claim": "from file", "min_confidence": 0.5}),
        encoding="utf-8",
    )

    settings = load_settings(
        cwd=tmp_path,
        overrides={"task": "from cli", "min_confidence": 0.9},
        use_dotenv=False,
        use_env=False,
    )

    assert settings.task == "from cli"
    assert settings.min_confidence == 0.9


def test_environment_overrides_beat_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variables win over the configuration file."""
    (tmp_path / CONFIG_FILENAME).write_text(
        json.dumps({"task": "from file", "model": "from-file"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTPROOF_MODEL", "from-env")

    settings = load_settings(cwd=tmp_path, use_dotenv=False, use_env=True)

    assert settings.model == "from-env"


def test_task_and_claim_can_live_in_files(tmp_path: Path) -> None:
    """task_file and claim_file are read relative to the config file."""
    (tmp_path / "task.md").write_text("Ship the release", encoding="utf-8")
    (tmp_path / "claim.md").write_text("Released it", encoding="utf-8")
    (tmp_path / CONFIG_FILENAME).write_text(
        json.dumps({"task_file": "task.md", "claim_file": "claim.md"}),
        encoding="utf-8",
    )

    settings = load_settings(cwd=tmp_path, use_dotenv=False, use_env=False)

    assert settings.task == "Ship the release"
    assert settings.claim == "Released it"


def test_workspace_is_resolved_relative_to_config(tmp_path: Path) -> None:
    """A relative workspace path is resolved against the config directory."""
    (tmp_path / "ws").mkdir()
    (tmp_path / CONFIG_FILENAME).write_text(
        json.dumps({"workspace": "./ws"}),
        encoding="utf-8",
    )

    settings = load_settings(cwd=tmp_path, use_dotenv=False, use_env=False)

    assert settings.workspace == tmp_path / "ws"


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    """Unknown configuration keys produce a helpful error."""
    path = tmp_path / CONFIG_FILENAME
    path.write_text(json.dumps({"nonsense": 1}), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="unknown key"):
        read_config_file(path)


def test_invalid_json_is_reported(tmp_path: Path) -> None:
    """Malformed JSON produces a helpful error."""
    path = tmp_path / CONFIG_FILENAME
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="not valid JSON"):
        read_config_file(path)


def test_invalid_min_confidence_is_rejected(tmp_path: Path) -> None:
    """Out-of-range values are rejected."""
    with pytest.raises(ConfigurationError, match="min_confidence"):
        load_settings(
            cwd=tmp_path,
            overrides={"min_confidence": 1.5},
            use_dotenv=False,
            use_env=False,
        )


def test_unknown_provider_is_rejected(tmp_path: Path) -> None:
    """An unknown provider name is rejected."""
    with pytest.raises(ConfigurationError, match="Unknown provider"):
        load_settings(
            cwd=tmp_path,
            overrides={"provider": "not-a-provider"},
            use_dotenv=False,
            use_env=False,
        )


def test_user_config_is_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The user-wide config file provides defaults for the project."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    user_file = user_config_path()
    user_file.parent.mkdir(parents=True)
    user_file.write_text(json.dumps({"provider": "openai"}), encoding="utf-8")

    settings = load_settings(cwd=tmp_path, use_dotenv=False, use_env=False)

    assert settings.provider == "openai"


def test_project_config_overrides_user_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The project config file wins over the user-wide config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    user_file = user_config_path()
    user_file.parent.mkdir(parents=True)
    user_file.write_text(
        json.dumps({"provider": "openai", "model": "user-model"}),
        encoding="utf-8",
    )
    (tmp_path / CONFIG_FILENAME).write_text(
        json.dumps({"provider": "anthropic"}),
        encoding="utf-8",
    )

    settings = load_settings(cwd=tmp_path, use_dotenv=False, use_env=False)

    assert settings.provider == "anthropic"
    assert settings.model == "user-model"


def test_save_config_file_roundtrip(tmp_path: Path) -> None:
    """Saving and reading a configuration file preserves the values."""
    path = tmp_path / "nested" / CONFIG_FILENAME
    save_config_file(path, {"task": "x", "claim": "y", "empty": None})

    data = read_config_file(path)
    assert data == {"task": "x", "claim": "y"}


def test_effective_model_falls_back_to_provider_default() -> None:
    """The effective model falls back to the provider's recommendation."""
    from agentproof.config import Settings

    assert Settings(provider="anthropic").effective_model == "claude-sonnet-5-5"
    assert Settings(provider="openai").effective_model == "gpt-6.1-sol"
    assert Settings(provider="openai", model="custom").effective_model == "custom"
