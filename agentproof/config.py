"""Configuration discovery, merging and persistence.

Configuration is layered. From lowest to highest precedence:

1. Built-in defaults.
2. The user-wide config file (``~/.config/agentproof/config.json``).
3. The project config file (``.agentproof.json`` in the current directory or
   any parent directory).
4. Environment variables (including those loaded from a ``.env`` file).
5. Explicit command-line options.

Every layer only overrides the keys it actually defines, so a project file can
override a single field without discarding the rest.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from agentproof.errors import ConfigurationError
from agentproof.providers.registry import get_spec

__all__ = [
    "CONFIG_FILENAME",
    "Settings",
    "apply_config_mapping",
    "describe_settings",
    "find_config_file",
    "load_dotenv_files",
    "load_settings",
    "read_config_file",
    "save_config_file",
    "user_config_path",
]


#: Name of the project-level configuration file.
CONFIG_FILENAME = ".agentproof.json"

#: Names of files that may hold API credentials. More specific files first.
DOTENV_FILENAMES: tuple[str, ...] = (".env.local", ".env")

#: Environment variables that override configuration file values.
ENV_OVERRIDES: dict[str, str] = {
    "AGENTPROOF_PROVIDER": "provider",
    "AGENTPROOF_MODEL": "model",
    "AGENTPROOF_BASE_URL": "base_url",
    "AGENTPROOF_TASK": "task",
    "AGENTPROOF_CLAIM": "claim",
    "AGENTPROOF_WORKSPACE": "workspace",
    "AGENTPROOF_MIN_CONFIDENCE": "min_confidence",
    "AGENTPROOF_MAX_FILES": "max_files",
    "AGENTPROOF_MAX_ARTIFACT_BYTES": "max_artifact_bytes",
    "AGENTPROOF_MAX_TOTAL_BYTES": "max_total_bytes",
    "AGENTPROOF_AUDITOR_INSTRUCTIONS": "auditor_instructions",
}

#: Keys accepted in a configuration file.
CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "task",
        "claim",
        "task_file",
        "claim_file",
        "workspace",
        "artifacts",
        "provider",
        "model",
        "base_url",
        "api_key",
        "api_key_env",
        "min_confidence",
        "max_artifact_bytes",
        "max_total_bytes",
        "max_files",
        "include",
        "exclude",
        "auditor_instructions",
        "temperature",
        "timeout",
        "max_retries",
        "max_tokens",
    }
)


@dataclass(slots=True)
class Settings:
    """The fully resolved configuration for a verification run.

    Attributes:
        task: The original task definition that the agent was given.
        claim: The agent's claim of what it accomplished.
        workspace: Directory (or file) containing the agent's work.
        artifacts: Extra explicit artifact paths to inspect.
        provider: Canonical provider name.
        model: Model identifier used for the audit.
        base_url: API root URL override.
        api_key: Explicit API key, if one was configured.
        min_confidence: Minimum confidence required for a SUCCESS verdict.
        max_artifact_bytes: Maximum bytes read per artifact.
        max_total_bytes: Maximum bytes read across all artifacts.
        max_files: Maximum number of artifacts collected.
        include: Glob patterns restricting which files are collected.
        exclude: Glob patterns vetoing files from the collection.
        auditor_instructions: Extra domain-specific instructions for the auditor.
        temperature: Optional sampling temperature override.
        timeout: Per-request timeout in seconds.
        max_retries: Number of retries for retryable provider failures.
        max_tokens: Maximum tokens the auditor may generate.
        config_path: Path of the configuration file that was loaded.
    """

    task: str | None = None
    claim: str | None = None
    workspace: Path | None = None
    artifacts: list[str] = field(default_factory=list)
    provider: str = "anthropic"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    min_confidence: float = 0.75
    max_artifact_bytes: int = 120_000
    max_total_bytes: int = 1_500_000
    max_files: int = 200
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    auditor_instructions: str = ""
    temperature: float | None = None
    timeout: float = 120.0
    max_retries: int = 3
    max_tokens: int = 8192
    config_path: Path | None = None

    @property
    def effective_model(self) -> str:
        """Return the model that will actually be used."""
        return (self.model or "").strip() or get_spec(self.provider).default_model

    def to_config_dict(self) -> dict[str, Any]:
        """Serialise the settings into a configuration-file friendly dict."""
        payload: dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name == "workspace":
                payload["workspace"] = str(value) if value else None
            elif item.name == "config_path":
                continue
            else:
                payload[item.name] = value
        return {key: value for key, value in payload.items() if value is not None}


def user_config_path() -> Path:
    """Return the path of the user-wide configuration file."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "agentproof" / "config.json"


def find_config_file(start: Path | None = None) -> Path | None:
    """Search ``start`` and its parents for a project configuration file.

    Args:
        start: Directory to start searching from. Defaults to the current
            working directory.

    Returns:
        The path of the nearest configuration file, or ``None``.
    """
    current = (start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_dotenv_files(start: Path | None = None) -> list[Path]:
    """Load ``.env`` files into the process environment.

    Values already present in the environment are preserved. Files are loaded
    from the nearest directory outward, so a project ``.env`` wins over one in
    a parent directory, and ``.env.local`` wins over ``.env``.

    Args:
        start: Directory to start searching from.

    Returns:
        The list of ``.env`` files that were loaded.
    """
    from dotenv import load_dotenv

    current = (start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent

    loaded: list[Path] = []
    directories = [current, *current.parents]
    for directory in directories:
        for name in DOTENV_FILENAMES:
            candidate = directory / name
            if candidate.is_file():
                load_dotenv(candidate, override=False)
                loaded.append(candidate)
    return loaded


def read_config_file(path: Path) -> dict[str, Any]:
    """Read and validate a configuration file.

    Args:
        path: Path of the configuration file.

    Returns:
        The parsed configuration mapping.

    Raises:
        ConfigurationError: If the file is not valid JSON or contains
            unknown keys.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Cannot read configuration file {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Configuration file {path} is not valid JSON: {exc.msg} (line {exc.lineno})"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigurationError(f"Configuration file {path} must contain a JSON object.")

    unknown = sorted(set(data) - CONFIG_KEYS)
    if unknown:
        raise ConfigurationError(
            f"Configuration file {path} contains unknown key(s): {', '.join(unknown)}. "
            f"Supported keys: {', '.join(sorted(CONFIG_KEYS))}"
        )
    return data


def save_config_file(path: Path, data: dict[str, Any]) -> Path:
    """Write a configuration file, creating parent directories as needed.

    Args:
        path: Destination path.
        data: Mapping to serialise as JSON.

    Returns:
        The path that was written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: value for key, value in data.items() if value is not None}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _as_str_list(value: Any, *, key: str) -> list[str]:
    """Coerce a configuration value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ConfigurationError(f"Configuration key '{key}' must be a string or a list of strings.")


def _coerce_float(value: Any, *, source: str) -> float:
    """Coerce a value to a float, reporting the offending setting."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{source} must be a number (got {value!r}).") from exc


def _coerce_int(value: Any, *, source: str) -> int:
    """Coerce a value to an integer, reporting the offending setting."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{source} must be an integer (got {value!r}).") from exc


def _read_text_file(path: Path, *, label: str) -> str:
    """Read a text file referenced from configuration.

    Args:
        path: Path of the file.
        label: Human-readable label used in error messages.

    Returns:
        The file content.

    Raises:
        ConfigurationError: If the file cannot be read.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        raise ConfigurationError(f"Cannot read {label} file {path}: {exc}") from exc


def apply_config_mapping(settings: Settings, data: dict[str, Any], base_dir: Path) -> None:
    """Apply a configuration mapping onto ``settings``."""
    if data.get("provider"):
        settings.provider = str(data["provider"]).strip().lower()
        get_spec(settings.provider)  # validate early

    if data.get("model"):
        settings.model = str(data["model"]).strip()
    if data.get("base_url"):
        settings.base_url = str(data["base_url"]).strip()
    if data.get("api_key"):
        settings.api_key = str(data["api_key"]).strip()
    if data.get("api_key_env"):
        env_name = str(data["api_key_env"]).strip()
        value = os.environ.get(env_name, "").strip()
        if value:
            settings.api_key = value
    if data.get("task"):
        settings.task = str(data["task"])
    if data.get("claim"):
        settings.claim = str(data["claim"])
    if data.get("workspace"):
        candidate = Path(str(data["workspace"])).expanduser()
        settings.workspace = candidate if candidate.is_absolute() else (base_dir / candidate)
    if "artifacts" in data:
        settings.artifacts = _as_str_list(data["artifacts"], key="artifacts")
    if "include" in data:
        settings.include = _as_str_list(data["include"], key="include")
    if "exclude" in data:
        settings.exclude = _as_str_list(data["exclude"], key="exclude")
    if data.get("auditor_instructions"):
        settings.auditor_instructions = str(data["auditor_instructions"])
    if "min_confidence" in data and data["min_confidence"] is not None:
        settings.min_confidence = _coerce_float(data["min_confidence"], source="min_confidence")
    if "max_artifact_bytes" in data and data["max_artifact_bytes"] is not None:
        settings.max_artifact_bytes = _coerce_int(
            data["max_artifact_bytes"], source="max_artifact_bytes"
        )
    if "max_total_bytes" in data and data["max_total_bytes"] is not None:
        settings.max_total_bytes = _coerce_int(data["max_total_bytes"], source="max_total_bytes")
    if "max_files" in data and data["max_files"] is not None:
        settings.max_files = _coerce_int(data["max_files"], source="max_files")
    if "temperature" in data and data["temperature"] is not None:
        settings.temperature = _coerce_float(data["temperature"], source="temperature")
    if "timeout" in data and data["timeout"] is not None:
        settings.timeout = _coerce_float(data["timeout"], source="timeout")
    if "max_retries" in data and data["max_retries"] is not None:
        settings.max_retries = _coerce_int(data["max_retries"], source="max_retries")
    if "max_tokens" in data and data["max_tokens"] is not None:
        settings.max_tokens = _coerce_int(data["max_tokens"], source="max_tokens")

    task_file = data.get("task_file")
    if task_file:
        path = Path(str(task_file)).expanduser()
        if not path.is_absolute():
            path = base_dir / path
        settings.task = _read_text_file(path, label="task")

    claim_file = data.get("claim_file")
    if claim_file:
        path = Path(str(claim_file)).expanduser()
        if not path.is_absolute():
            path = base_dir / path
        settings.claim = _read_text_file(path, label="claim")


def _apply_env(settings: Settings) -> None:
    """Apply environment variable overrides onto ``settings``."""
    for env_name, key in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if not value:
            continue
        if key == "min_confidence":
            settings.min_confidence = _coerce_float(value, source=env_name)
        elif key in {"max_files", "max_artifact_bytes", "max_total_bytes"}:
            setattr(settings, key, _coerce_int(value, source=env_name))
        elif key == "workspace":
            settings.workspace = Path(value).expanduser()
        elif key == "provider":
            settings.provider = value.strip().lower()
            get_spec(settings.provider)
        else:
            setattr(settings, key, value.strip())


def load_settings(
    *,
    cwd: Path | None = None,
    overrides: dict[str, Any] | None = None,
    use_dotenv: bool = True,
    use_env: bool = True,
) -> Settings:
    """Resolve the effective settings for a run.

    Args:
        cwd: Directory used as the starting point for config discovery.
        overrides: Explicitly provided command-line values. Keys with a
            ``None`` value are ignored, so they do not clobber lower layers.
        use_dotenv: Whether ``.env`` files should be loaded.
        use_env: Whether environment variables should be applied.

    Returns:
        The resolved settings.

    Raises:
        ConfigurationError: If a configuration file is malformed or a value
            cannot be coerced.
    """
    start = (cwd or Path.cwd()).expanduser().resolve()
    settings = Settings()

    if use_dotenv:
        load_dotenv_files(start)

    user_path = user_config_path()
    if user_path.is_file():
        apply_config_mapping(settings, read_config_file(user_path), user_path.parent)

    project_path = find_config_file(start)
    if project_path is not None:
        apply_config_mapping(settings, read_config_file(project_path), project_path.parent)
        settings.config_path = project_path

    if use_env:
        _apply_env(settings)

    if overrides:
        apply_config_mapping(settings, {k: v for k, v in overrides.items() if v is not None}, start)

    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    """Validate resolved settings.

    Args:
        settings: The settings to validate.

    Raises:
        ConfigurationError: If a value is out of range or invalid.
    """
    get_spec(settings.provider)

    if not 0.0 <= settings.min_confidence <= 1.0:
        raise ConfigurationError(
            f"min_confidence must be between 0.0 and 1.0 (got {settings.min_confidence})."
        )
    if settings.max_files < 1:
        raise ConfigurationError("max_files must be at least 1.")
    if settings.max_artifact_bytes < 1:
        raise ConfigurationError("max_artifact_bytes must be at least 1.")
    if settings.max_total_bytes < 1:
        raise ConfigurationError("max_total_bytes must be at least 1.")
    if settings.timeout <= 0:
        raise ConfigurationError("timeout must be greater than 0.")
    if settings.max_retries < 0:
        raise ConfigurationError("max_retries cannot be negative.")
    if settings.max_tokens < 256:
        raise ConfigurationError("max_tokens must be at least 256.")
    if settings.temperature is not None and not 0.0 <= settings.temperature <= 2.0:
        raise ConfigurationError("temperature must be between 0.0 and 2.0.")
    if settings.model is not None and not settings.model.strip():
        raise ConfigurationError("model cannot be empty.")


def describe_settings(settings: Settings) -> list[tuple[str, str]]:
    """Return a display-friendly description of the resolved settings.

    Args:
        settings: The resolved settings.

    Returns:
        A list of ``(label, value)`` pairs.
    """
    rows = [
        ("Provider", settings.provider),
        ("Model", settings.effective_model),
        ("Workspace", str(settings.workspace) if settings.workspace else "(not set)"),
        ("Task", "set" if settings.task else "(not set)"),
        ("Claim", "set" if settings.claim else "(not set)"),
        ("Min confidence", f"{settings.min_confidence:.0%}"),
        ("Config file", str(settings.config_path) if settings.config_path else "(none)"),
    ]
    if settings.artifacts:
        rows.append(("Extra artifacts", ", ".join(settings.artifacts)))
    return rows
