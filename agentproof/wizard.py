"""Interactive setup wizard.

The wizard walks the user through creating a project configuration file. It is
deliberately forgiving: every question has a sensible default and the user can
abort at any point without leaving a half-written file behind.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentproof.config import CONFIG_FILENAME, save_config_file
from agentproof.providers.registry import get_spec, provider_names

__all__ = ["prompt_multiline", "run_wizard"]


def prompt_multiline(label: str, *, default: str = "") -> str:
    """Ask the user for a possibly multi-line answer.

    The user types lines and finishes with an empty line.

    Args:
        label: The question to ask.
        default: Value returned when the user submits nothing.

    Returns:
        The collected text.
    """
    console = Console()
    console.print(f"[bold]{label}[/bold]")
    if default:
        console.print(f"[dim](default: {default})[/dim]")
    console.print("[dim]Enter one or more lines, then press Enter on an empty line.[/dim]")

    lines: list[str] = []
    stream = sys.stdin
    while stream is not None:
        try:
            line = stream.readline()
        except (KeyboardInterrupt, EOFError, ValueError):
            break
        if line == "":
            break
        stripped = line.rstrip("\n")
        if not stripped.strip():
            break
        lines.append(stripped)

    answer = "\n".join(lines).strip()
    return answer or default


def _prompt_optional(label: str, *, default: str = "") -> str:
    """Ask the user for an optional single-line answer.

    Args:
        label: The question to ask.
        default: Value returned when the user submits nothing.

    Returns:
        The collected text.
    """
    value = click.prompt(label, default=default, show_default=bool(default), type=str)
    return value.strip()


def run_wizard(
    *,
    console: Console,
    config_path: Path | None = None,
    provider: str | None = None,
    model: str | None = None,
    force: bool = False,
) -> Path:
    """Run the interactive setup wizard.

    Args:
        console: Console used for output.
        config_path: Where to write the configuration file. Defaults to
            ``.agentproof.json`` in the current directory.
        provider: Pre-selected provider name.
        model: Pre-selected model name.
        force: Overwrite an existing configuration file without asking.

    Returns:
        The path of the configuration file that was written.

    Raises:
        click.Abort: If the user aborts the wizard.
    """
    target = config_path or (Path.cwd() / CONFIG_FILENAME)

    if (
        target.exists()
        and not force
        and not click.confirm(f"{target} already exists. Overwrite it?", default=False)
    ):
        raise click.Abort("Aborted: the existing configuration file was left untouched.")

    console.print(
        Panel(
            "This wizard creates a configuration file describing the task, the "
            "agent's claim, and where its output lives.",
            title="AgentProof setup",
            border_style="cyan",
        )
    )
    console.print()

    task = prompt_multiline("1/6  What was the agent asked to do? (the task definition)")
    if not task:
        raise click.Abort("Aborted: a task definition is required.")

    claim = prompt_multiline(
        "2/6  What did the agent claim it did? (paste the agent's final message)"
    )
    if not claim:
        raise click.Abort("Aborted: the agent's claim is required.")

    workspace = _prompt_optional(
        "3/6  Where did the agent work? (directory with its output)", default="."
    )

    artifacts = _prompt_optional(
        "4/6  Extra log or output files to include (comma separated, optional)", default=""
    )

    if provider:
        chosen_provider = provider
        console.print(f"[dim]Using provider {chosen_provider}.[/dim]")
    else:
        chosen_provider = click.prompt(
            "5/6  Which auditor model provider should be used?",
            type=click.Choice(provider_names(), case_sensitive=False),
            default="anthropic",
        ).lower()
    spec = get_spec(chosen_provider)

    if model:
        chosen_model = model
    else:
        chosen_model = _prompt_optional(
            f"6/6  Model to use ({spec.default_model} recommended)", default=spec.default_model
        )

    confidence = click.prompt(
        "Minimum confidence required for a SUCCESS verdict",
        default=0.75,
        type=float,
    )

    console.print()
    console.print("[bold]Credentials[/bold]")
    console.print(
        f"Set [bold]{spec.env_var}[/bold] in your environment before running the check, "
        f"for example:\n\n    export {spec.env_var}=sk-...\n"
    )
    if click.confirm("Store the API key in a local .env file instead?", default=False):
        key = click.prompt(f"{spec.env_var}", hide_input=True, default="", show_default=False)
        if key.strip():
            _write_env_file(Path.cwd() / ".env", spec.env_var, key.strip())
            console.print(f"[green]Wrote[/green] {Path.cwd() / '.env'}")

    data: dict[str, object] = {
        "task": task,
        "claim": claim,
        "workspace": workspace,
        "provider": chosen_provider,
        "model": chosen_model,
        "min_confidence": confidence,
    }
    if artifacts:
        data["artifacts"] = [item.strip() for item in artifacts.split(",") if item.strip()]

    save_config_file(target, data)

    console.print()
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Config file", str(target))
    table.add_row("Provider", chosen_provider)
    table.add_row("Model", chosen_model)
    table.add_row("Workspace", workspace)
    console.print(Panel(table, title="Setup complete", border_style="green"))
    console.print()
    console.print("Run [bold]agentproof --check[/bold] to verify the claim.")
    console.print()
    return target


def _write_env_file(path: Path, key: str, value: str) -> None:
    """Append or replace a key in a ``.env`` file.

    The file is created with owner-only permissions, since it holds a secret.

    Args:
        path: The ``.env`` file.
        key: The variable name.
        value: The variable value.
    """
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [line for line in existing.splitlines() if not line.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    path.chmod(0o600)
