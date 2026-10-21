"""Command-line interface for AgentProof.

``agentproof --check`` runs the full workflow: gather context, collect the
agent's artifacts, ask an independent auditor model to verify the claim, and
print a verdict. The process exit code reflects the verdict so the tool can be
used directly in CI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentproof import __version__
from agentproof.config import (
    Settings,
    apply_config_mapping,
    describe_settings,
    find_config_file,
    load_settings,
    read_config_file,
)
from agentproof.context import build_context
from agentproof.errors import (
    AgentProofError,
    ConfigurationError,
    MissingCredentialsError,
    ProviderError,
    ResponseParseError,
    WorkspaceError,
)
from agentproof.models import Verdict, VerificationReport
from agentproof.prompts import build_system_prompt, build_user_prompt
from agentproof.providers.registry import create_provider, get_spec, provider_names
from agentproof.report import render_json_report, render_report
from agentproof.verifier import Verifier
from agentproof.wizard import prompt_multiline, run_wizard

__all__ = ["main"]


#: Exit code used when the claim is verified.
EXIT_SUCCESS = 0
#: Exit code used when the claim could not be verified.
EXIT_FAILED = 1
#: Exit code used for configuration or usage problems.
EXIT_USAGE = 2
#: Exit code used when the LLM provider failed.
EXIT_PROVIDER = 3
#: Exit code used when the auditor's answer could not be understood.
EXIT_INCONCLUSIVE = 4


def _build_console(no_color: bool) -> Console:
    """Create the console used for all output.

    Args:
        no_color: Whether to disable ANSI colours.

    Returns:
        The configured console.
    """
    return Console(no_color=no_color, soft_wrap=False)


def _load_settings(options: dict[str, Any]) -> Settings:
    """Resolve settings, honouring an explicit ``--config`` file.

    Args:
        options: The parsed command-line options.

    Returns:
        The resolved settings.
    """
    config_path: Path | None = options.get("config_path")
    if config_path is None:
        return _settings_from_options(options)

    data = read_config_file(config_path)
    overrides = _option_overrides(options)
    settings = Settings()
    apply_config_mapping(settings, data, config_path.parent)
    settings.config_path = config_path
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _settings_from_options(options: dict[str, Any]) -> Settings:
    """Resolve settings from config discovery plus command-line overrides.

    Args:
        options: The parsed command-line options.

    Returns:
        The resolved settings.
    """
    return load_settings(overrides=_option_overrides(options))


def _option_overrides(options: dict[str, Any]) -> dict[str, Any]:
    """Turn command-line options into configuration overrides.

    Only explicitly supplied options are included, so lower-precedence layers
    are not clobbered.

    Args:
        options: The parsed command-line options.

    Returns:
        The override mapping.
    """
    overrides: dict[str, Any] = {
        "task": options.get("task"),
        "claim": options.get("claim"),
        "provider": options.get("provider"),
        "model": options.get("model"),
        "base_url": options.get("base_url"),
        "min_confidence": options.get("min_confidence"),
        "max_files": options.get("max_files"),
        "max_artifact_bytes": options.get("max_artifact_bytes"),
        "max_total_bytes": options.get("max_total_bytes"),
        "auditor_instructions": options.get("auditor_instructions"),
        "temperature": options.get("temperature"),
        "timeout": options.get("timeout"),
        "max_retries": options.get("max_retries"),
        "max_tokens": options.get("max_tokens"),
    }

    task_file: Path | None = options.get("task_file")
    if task_file:
        overrides["task_file"] = str(task_file)
    claim_file: Path | None = options.get("claim_file")
    if claim_file:
        overrides["claim_file"] = str(claim_file)
    workspace: Path | None = options.get("workspace")
    if workspace:
        overrides["workspace"] = str(workspace)

    includes = list(options.get("includes") or [])
    excludes = list(options.get("excludes") or [])
    artifacts = [str(item) for item in (options.get("artifacts") or [])]
    if includes:
        overrides["include"] = includes
    if excludes:
        overrides["exclude"] = excludes
    if artifacts:
        overrides["artifacts"] = artifacts
    return {key: value for key, value in overrides.items() if value is not None}


def _read_file_text(path: Path, label: str) -> str:
    """Read a UTF-8 text file, raising a friendly error on failure.

    Args:
        path: The file to read.
        label: Human-readable label used in the error message.

    Returns:
        The file content.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        raise ConfigurationError(f"Cannot read {label} file {path}: {exc}") from exc


def _resolve_inputs(
    settings: Settings,
    options: dict[str, Any],
    console: Console,
) -> tuple[str | None, str | None, Path | None]:
    """Fill in any missing task, claim, or workspace.

    When the session is interactive the user is asked for the missing values.
    In a non-interactive session a clear error is raised instead.

    Args:
        settings: The resolved settings.
        options: The parsed command-line options.
        console: Console used for prompts.

    Returns:
        The resolved ``(task, claim, workspace)`` triple.
    """
    task = options.get("task") or settings.task
    if options.get("task_file"):
        task = _read_file_text(options["task_file"], "task")
    claim = options.get("claim") or settings.claim
    if options.get("claim_file"):
        claim = _read_file_text(options["claim_file"], "claim")
    workspace = options.get("workspace") or settings.workspace

    interactive = sys.stdin.isatty()

    if not task:
        if not interactive:
            raise ConfigurationError(
                "No task definition was provided and the session is not interactive.\n"
                "  Provide it with --task/--task-file, set 'task' in "
                f"{'.agentproof.json'}, or export AGENTPROOF_TASK."
            )
        console.print()
        console.print("[bold yellow]No task definition found.[/bold yellow]")
        task = prompt_multiline("What was the agent asked to do?")

    if not claim:
        if not interactive:
            raise ConfigurationError(
                "No agent claim was provided and the session is not interactive.\n"
                "  Provide it with --claim/--claim-file, set 'claim' in "
                ".agentproof.json, or export AGENTPROOF_CLAIM."
            )
        console.print()
        console.print("[bold yellow]No agent claim found.[/bold yellow]")
        claim = prompt_multiline("What did the agent claim it did?")

    if workspace is None:
        if not interactive:
            raise ConfigurationError(
                "No workspace was provided and the session is not interactive.\n"
                "  Provide it with --workspace, set 'workspace' in .agentproof.json, "
                "or export AGENTPROOF_WORKSPACE."
            )
        workspace = Path(
            click.prompt("Which directory contains the agent's output?", default=".")
        ).expanduser()

    return task, claim, workspace


def _build_context_panel(settings: Settings, artifact_summary: str) -> Panel:
    """Build the panel describing what is about to be audited.

    Args:
        settings: The resolved settings.
        artifact_summary: One-line summary of the collected artifacts.

    Returns:
        The renderable panel.
    """
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold dim", width=18)
    table.add_column()
    table.add_row("Provider", settings.provider)
    table.add_row("Model", settings.effective_model)
    table.add_row("Artifacts", artifact_summary)
    table.add_row("Threshold", f"{settings.min_confidence:.0%} confidence required for SUCCESS")
    return Panel(table, title="Auditing with", border_style="cyan", padding=(0, 2))


def _render_quiet(console: Console, report: VerificationReport) -> None:
    """Print a one-line summary of the verdict.

    Args:
        console: Console to print to.
        report: The report to summarise.
    """
    style = "bold black on green" if report.verdict is Verdict.SUCCESS else "bold white on red"
    badge = f" {report.verdict.label} "
    console.print(f"[{style}]{badge}[/{style}] confidence {report.confidence:.0%}", markup=False)
    console.print(report.summary, style="dim")


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 100},
)
@click.option("--check", "check_flag", is_flag=True, help="Run the verification workflow.")
@click.option("--task", type=str, default=None, help="The task definition given to the agent.")
@click.option(
    "--task-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Read the task definition from a file.",
)
@click.option("--claim", type=str, default=None, help="The agent's claim of what it did.")
@click.option(
    "--claim-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Read the agent's claim from a file.",
)
@click.option(
    "--workspace",
    type=click.Path(file_okay=True, path_type=Path),
    default=None,
    help="Directory (or file) containing the agent's output.",
)
@click.option(
    "--artifact",
    "artifacts",
    multiple=True,
    type=click.Path(path_type=Path),
    help="Extra artifact to inspect (repeatable).",
)
@click.option(
    "--provider",
    type=click.Choice(provider_names(), case_sensitive=False),
    default=None,
    help="LLM provider used as the independent auditor.",
)
@click.option("--model", type=str, default=None, help="Model used as the independent auditor.")
@click.option("--base-url", type=str, default=None, help="Override the provider API base URL.")
@click.option(
    "--min-confidence",
    type=float,
    default=None,
    help="Minimum confidence required for a SUCCESS verdict (0.0-1.0).",
)
@click.option("--max-files", type=int, default=None, help="Maximum number of artifacts to collect.")
@click.option(
    "--max-artifact-bytes",
    type=int,
    default=None,
    help="Maximum bytes read from a single artifact.",
)
@click.option(
    "--max-total-bytes",
    type=int,
    default=None,
    help="Maximum bytes read across all artifacts.",
)
@click.option("--include", "includes", multiple=True, help="Glob pattern of files to include.")
@click.option("--exclude", "excludes", multiple=True, help="Glob pattern of files to exclude.")
@click.option(
    "--auditor-instructions",
    type=str,
    default=None,
    help="Extra domain context for the auditor.",
)
@click.option(
    "--temperature", type=float, default=None, help="Sampling temperature for the auditor."
)
@click.option("--timeout", type=float, default=None, help="API timeout in seconds.")
@click.option("--max-retries", type=int, default=None, help="Retries for transient API failures.")
@click.option(
    "--max-tokens", type=int, default=None, help="Maximum tokens the auditor may generate."
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Use a specific configuration file instead of auto-discovery.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit the report as JSON.")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the auditor prompt and exit without calling the API.",
)
@click.option("--quiet", "-q", is_flag=True, help="Print only the verdict line.")
@click.option("--no-color", is_flag=True, help="Disable coloured output.")
@click.version_option(__version__, "-V", "--version", prog_name="agentproof")
@click.pass_context
def main(ctx: click.Context, /, check_flag: bool, **options: Any) -> None:
    """Verify that an AI agent actually completed the task it claimed to complete.

    Run `agentproof --check` to audit the current workspace. Use
    `agentproof init` to create a configuration file interactively, and
    `agentproof doctor` to diagnose configuration problems.
    """
    options["check_flag"] = check_flag
    ctx.obj = options

    if ctx.invoked_subcommand is not None:
        return

    console = _build_console(bool(options.get("no_color")))
    code = _execute_check(options, console)
    ctx.exit(code)


@main.command("init")
@click.option(
    "--path",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Where to write the configuration file.",
)
@click.option(
    "--provider",
    type=click.Choice(provider_names(), case_sensitive=False),
    default=None,
    help="Pre-select the auditor provider.",
)
@click.option("--model", type=str, default=None, help="Pre-select the auditor model.")
@click.option("--force", is_flag=True, help="Overwrite an existing configuration file.")
@click.option("--no-color", is_flag=True, help="Disable coloured output.")
def init_command(
    config_path: Path | None,
    provider: str | None,
    model: str | None,
    force: bool,
    no_color: bool,
) -> None:
    """Create a configuration file interactively."""
    console = _build_console(no_color)
    try:
        run_wizard(
            console=console,
            config_path=config_path,
            provider=provider.lower() if provider else None,
            model=model,
            force=force,
        )
    except click.Abort as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise SystemExit(EXIT_USAGE) from exc


@main.command("doctor")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Use a specific configuration file instead of auto-discovery.",
)
@click.option(
    "--provider",
    type=click.Choice(provider_names(), case_sensitive=False),
    default=None,
    help="Provider to diagnose.",
)
@click.option("--no-color", is_flag=True, help="Disable coloured output.")
def doctor_command(config_path: Path | None, provider: str | None, no_color: bool) -> None:
    """Check that AgentProof is configured correctly."""
    console = _build_console(no_color)
    problems: list[str] = []

    console.print()
    console.print("[bold]AgentProof environment[/bold]")
    console.print(f"  version      : {__version__}")
    console.print(f"  python       : {sys.version.split()[0]}")

    try:
        settings = _load_settings({"config_path": config_path}) if config_path else load_settings()
        if provider:
            settings.provider = provider.lower()
    except AgentProofError as exc:
        console.print(f"  [red]configuration error:[/red] {exc}")
        raise SystemExit(EXIT_USAGE) from exc

    discovered = find_config_file()
    console.print(f"  config file  : {discovered if discovered else '[dim]none found[/dim]'}")
    if settings.config_path:
        console.print(f"  using        : {settings.config_path}")

    console.print()
    console.print("[bold]Resolved settings[/bold]")
    for label, value in describe_settings(settings):
        console.print(f"  {label:<16}: {value}")

    spec = get_spec(settings.provider)
    api_key = settings.api_key or os.environ.get(spec.env_var, "")
    console.print()
    console.print("[bold]Credentials[/bold]")
    if api_key:
        masked = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 12 else "set"
        console.print(f"  {spec.env_var:<16}: [green]present[/green] ({masked})")
    else:
        console.print(f"  {spec.env_var:<16}: [red]missing[/red]")
        problems.append(
            f"No API key for provider '{spec.name}'. Export {spec.env_var} or add it "
            "to a .env file."
        )

    if not settings.task:
        problems.append("No task definition configured. Run 'agentproof init'.")
    if not settings.claim:
        problems.append("No agent claim configured. Run 'agentproof init'.")

    console.print()
    if problems:
        console.print("[bold red]Problems found[/bold red]")
        for problem in problems:
            console.print(f"  [red]•[/red] {problem}")
        console.print()
        console.print("Run [bold]agentproof init[/bold] to create a configuration file.")
        console.print()
        raise SystemExit(EXIT_USAGE)

    console.print(
        "[bold green]Everything looks good.[/bold green] Run [bold]agentproof --check[/bold]."
    )
    console.print()


def _execute_check(options: dict[str, Any], console: Console) -> int:
    """Run the full verification workflow.

    Args:
        options: The parsed command-line options.
        console: Console for output.

    Returns:
        The process exit code.
    """
    try:
        settings = _load_settings(options)
        task, claim, workspace = _resolve_inputs(settings, options, console)
        context = build_context(settings, task=task, claim=claim, workspace=workspace)
    except (ConfigurationError, WorkspaceError) as exc:
        _print_error(console, exc)
        return EXIT_USAGE
    except AgentProofError as exc:
        _print_error(console, exc)
        return EXIT_USAGE

    if not options.get("quiet") and not options.get("json_output"):
        context_panel = _build_context_panel(settings, context.artifact_set.summary_line())
    else:
        context_panel = None

    if options.get("dry_run"):
        system = build_system_prompt(settings)
        user = build_user_prompt(
            task=context.task,
            claim=context.claim,
            artifact_set=context.artifact_set,
            workspace=str(context.workspace),
        )
        console.print(Panel(system, title="System prompt", border_style="magenta"))
        console.print()
        console.print(Panel(user, title="User prompt", border_style="magenta"))
        return EXIT_SUCCESS

    try:
        provider = create_provider(
            provider=settings.provider,
            api_key=settings.api_key,
            model=settings.model,
            base_url=settings.base_url,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
        )
    except MissingCredentialsError as exc:
        _print_error(console, exc, hint=f"export {exc.env_var}=your-key-here")
        return EXIT_USAGE
    except ConfigurationError as exc:
        _print_error(console, exc)
        return EXIT_USAGE

    verifier = Verifier(provider, settings)
    try:
        report = verifier.verify(context)
    except ResponseParseError as exc:
        _print_error(
            console,
            exc,
            hint="The auditor returned an unusable answer. Try again, or use --model to "
            "select a different auditor.",
        )
        return EXIT_INCONCLUSIVE
    except ProviderError as exc:
        _print_error(console, exc, hint="Check your API key, model name, and network access.")
        return EXIT_PROVIDER
    finally:
        provider.close()

    if options.get("json_output"):
        render_json_report(report, console)
    elif options.get("quiet"):
        _render_quiet(console, report)
    else:
        render_report(report, console, context=context_panel)

    return EXIT_SUCCESS if report.verdict is Verdict.SUCCESS else EXIT_FAILED


def _print_error(console: Console, exc: Exception, *, hint: str | None = None) -> None:
    """Print a friendly error message.

    Args:
        console: Console to print to.
        exc: The exception to report.
        hint: Optional actionable next step.
    """
    console.print()
    console.print(f"[bold red]Error:[/bold red] {exc}")
    if hint:
        console.print(f"[dim]Hint: {hint}[/dim]")
    console.print()


if __name__ == "__main__":  # pragma: no cover
    main()
