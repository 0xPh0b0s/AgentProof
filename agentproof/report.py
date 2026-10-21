"""Terminal rendering of verification reports.

The report is designed to be readable at a glance: a single status badge with
a confidence score, then the evidence - what was verified, what was not, and
where the claim and the artifacts disagree.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agentproof.models import CheckStatus, Verdict, VerificationReport

__all__ = [
    "STATUS_STYLES",
    "render_json_report",
    "render_report",
    "status_style",
]


#: Style used for each check status.
STATUS_STYLES: dict[CheckStatus, str] = {
    CheckStatus.VERIFIED: "bold green",
    CheckStatus.PARTIAL: "bold yellow",
    CheckStatus.FAILED: "bold red",
    CheckStatus.MISSING: "bold red",
    CheckStatus.UNVERIFIABLE: "bold magenta",
}

#: Short labels used in the status column.
STATUS_LABELS: dict[CheckStatus, str] = {
    CheckStatus.VERIFIED: "VERIFIED",
    CheckStatus.PARTIAL: "PARTIAL",
    CheckStatus.FAILED: "FAILED",
    CheckStatus.MISSING: "MISSING",
    CheckStatus.UNVERIFIABLE: "UNVERIFIABLE",
}


def status_style(status: CheckStatus) -> str:
    """Return the rich style for a check status.

    Args:
        status: The status to style.

    Returns:
        A rich style string.
    """
    return STATUS_STYLES.get(status, "white")


def _confidence_bar(score: float, width: int = 24, *, style: str = "bold green") -> Text:
    """Render a text-based confidence bar.

    Args:
        score: A confidence score between 0.0 and 1.0.
        width: Number of characters in the bar.
        style: Rich style applied to the filled portion.

    Returns:
        The rendered bar.
    """
    filled = round(max(0.0, min(1.0, score)) * width)
    bar = Text()
    bar.append("█" * filled, style=style)
    bar.append("░" * (width - filled), style="dim")
    return bar


def _verdict_panel(report: VerificationReport) -> Panel:
    """Build the headline panel with the status badge and confidence.

    Args:
        report: The report to render.

    Returns:
        A renderable panel.
    """
    if report.verdict is Verdict.SUCCESS:
        badge_style = "bold black on green"
        bar_style = "bold green"
        border_style = "green"
    else:
        badge_style = "bold white on red"
        bar_style = "bold red"
        border_style = "red"

    badge = Text(f" {report.verdict.label} ", style=badge_style)

    header = Text()
    header.append_text(badge)
    header.append("   ")
    header.append("Confidence ", style="bold")
    header.append_text(_confidence_bar(report.confidence, style=bar_style))
    header.append(f"  {report.confidence:.0%}", style="bold")

    body: list[RenderableType] = [header, ""]
    if report.summary:
        body.append(Text(report.summary, style=border_style))
    else:
        body.append(Text("The auditor did not provide a summary.", style="dim italic"))

    counts = Text()
    counts.append(f"{report.verified_count}", style="bold green")
    counts.append(" verified  ·  ")
    counts.append(f"{report.failed_count}", style="bold red")
    counts.append(" unsatisfied", style="dim")
    counts.append(f"  ·  {len(report.checks)} requirement(s) checked", style="dim")
    body.append("")
    body.append(counts)

    return Panel(
        Group(*body),
        title="Verification Result",
        border_style=border_style,
        padding=(1, 2),
    )


def _checks_table(report: VerificationReport) -> Table:
    """Build the requirement-by-requirement evidence table.

    Args:
        report: The report to render.

    Returns:
        A renderable table.
    """
    table = Table(
        show_header=True,
        header_style="bold",
        expand=False,
        pad_edge=False,
        box=None,
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Status", width=13)
    table.add_column("Requirement", ratio=3, min_width=20)
    table.add_column("Evidence", ratio=5, min_width=30)

    if not report.checks:
        table.add_row("-", "[dim]n/a[/dim]", "[dim]No checks reported[/dim]", "")
        return table

    for index, check in enumerate(report.checks, start=1):
        evidence = Text(check.evidence or "[no evidence provided]", style="dim")
        if check.source:
            evidence.append("\n")
            evidence.append(check.source, style="dim italic")
        label = STATUS_LABELS.get(check.status, check.status.value)
        table.add_row(
            str(index),
            Text(label, style=status_style(check.status)),
            Text(check.requirement),
            evidence,
        )
    return table


def _bullet_panel(title: str, items: list[str], style: str) -> Panel | None:
    """Build a bulleted panel, or ``None`` when there is nothing to show.

    Args:
        title: Panel title.
        items: Bullet items.
        style: Style applied to the items.

    Returns:
        The panel, or ``None``.
    """
    if not items:
        return None
    body = Group(*[Text(f"• {item}", style=style) for item in items])
    return Panel(body, title=title, border_style=style, padding=(0, 2))


def _footer(report: VerificationReport) -> Text:
    """Build the metadata footer.

    Args:
        report: The report to render.

    Returns:
        The rendered footer.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    usage = f"{report.prompt_tokens + report.completion_tokens} tokens"
    footer = Text()
    footer.append(f"auditor: {report.provider or 'unknown'}", style="dim")
    footer.append(" · ", style="dim")
    footer.append(f"model: {report.model or 'unknown'}", style="dim")
    footer.append(" · ", style="dim")
    footer.append(f"artifacts scanned: {report.artifacts_scanned}", style="dim")
    footer.append(" · ", style="dim")
    footer.append(f"usage: {usage}", style="dim")
    footer.append(" · ", style="dim")
    footer.append(timestamp, style="dim")
    return footer


def render_report(
    report: VerificationReport,
    console: Console | None = None,
    *,
    context: RenderableType | None = None,
) -> None:
    """Render a verification report to the terminal.

    Args:
        report: The report to render.
        console: Console to print to. A new console is created when omitted.
        context: Optional renderable shown between the title and the verdict,
            typically a summary of what was audited.
    """
    out = console or Console()
    out.print()

    out.print(
        Panel(
            Text("Independent verification of an AI agent's claimed completion", style="dim"),
            title="[bold]AgentProof[/bold]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    out.print()
    if context is not None:
        out.print(context)
        out.print()
    out.print(_verdict_panel(report))

    if report.checks:
        out.print()
        out.print(Text("Evidence breakdown", style="bold"))
        out.print(_checks_table(report))

    panels = [
        _bullet_panel("Discrepancies", report.discrepancies, "red"),
        _bullet_panel("Hallucinated claims", report.hallucinations, "bold red"),
        _bullet_panel("Missing items", report.missing_items, "yellow"),
        _bullet_panel("Recommendations", report.recommendations, "cyan"),
    ]
    present = [panel for panel in panels if panel is not None]
    if present:
        out.print()
        for panel in present:
            out.print(panel)

    if report.notes:
        out.print()
        out.print(
            Panel(
                Text(report.notes, style="dim"),
                title="Auditor notes",
                border_style="dim",
                padding=(0, 2),
            )
        )

    out.print()
    out.print(_footer(report))
    out.print()


def render_json_report(report: VerificationReport, console: Console | None = None) -> None:
    """Render a verification report as JSON, for CI consumption.

    Args:
        report: The report to render.
        console: Console to print to. A new console is created when omitted.
    """
    out = console or Console()
    out.print_json(json.dumps(report.to_dict(), indent=2))
