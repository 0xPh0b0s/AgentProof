"""The verification engine.

The engine is intentionally thin: it assembles the prompt, asks the auditor
model for a structured verdict, validates the answer, and applies two
conservative guard rails that no amount of auditor confidence can override:

* a SUCCESS verdict with a confidence below the configured threshold is
  downgraded to FAILED;
* a SUCCESS verdict that contains no requirement-level checks at all is
  downgraded to FAILED, because nothing has been evidenced;
* a SUCCESS verdict that contains any unsatisfied check is downgraded to
  FAILED.
"""

from __future__ import annotations

import json
from typing import Any

from agentproof.config import Settings
from agentproof.context import VerificationContext
from agentproof.errors import ResponseParseError
from agentproof.models import CheckStatus, Usage, Verdict, VerificationCheck, VerificationReport
from agentproof.prompts import REPORT_JSON_SCHEMA, build_system_prompt, build_user_prompt
from agentproof.providers.base import Provider
from agentproof.utils import extract_json_object

__all__ = ["Verifier", "parse_report_payload", "parse_report_text"]


#: Reminder appended when the first response could not be parsed.
_RETRY_REMINDER = (
    "Your previous reply could not be parsed as JSON. Reply with a single raw JSON "
    "object that matches the required schema. Output the JSON object only - no "
    "prose, no Markdown code fences, no explanation."
)


class Verifier:
    """Run the audit and turn the auditor's answer into a report.

    Args:
        provider: The LLM backend used as auditor.
        settings: The resolved settings.
    """

    def __init__(self, provider: Provider, settings: Settings) -> None:
        """Store the auditor provider and the resolved settings."""
        self.provider = provider
        self.settings = settings

    def verify(self, context: VerificationContext) -> VerificationReport:
        """Audit the agent's claim against the collected artifacts.

        Args:
            context: The verification context.

        Returns:
            The verification report.

        Raises:
            ResponseParseError: If the auditor's answer cannot be parsed.
            ProviderError: If the provider request fails.
        """
        system = build_system_prompt(self.settings)
        user = build_user_prompt(
            task=context.task,
            claim=context.claim,
            artifact_set=context.artifact_set,
            workspace=str(context.workspace),
        )

        response = self.provider.complete(
            system=system,
            user=user,
            max_tokens=self.settings.max_tokens,
            temperature=self.settings.temperature,
            json_schema=REPORT_JSON_SCHEMA,
        )

        try:
            payload = parse_report_text(response.text)
        except ResponseParseError:
            # One corrective retry: auditors occasionally wrap JSON in prose.
            retry = self.provider.complete(
                system=system,
                user=f"{user}\n\n{_RETRY_REMINDER}",
                max_tokens=self.settings.max_tokens,
                temperature=self.settings.temperature,
                json_schema=REPORT_JSON_SCHEMA,
            )
            payload = parse_report_text(retry.text)
            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens + retry.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens + retry.usage.completion_tokens,
            )
            model = retry.model
        else:
            usage = response.usage
            model = response.model

        report = parse_report_payload(payload)
        report.provider = self.provider.spec.name
        report.model = model
        report.artifacts_scanned = context.artifact_count
        report.prompt_tokens = usage.prompt_tokens
        report.completion_tokens = usage.completion_tokens

        self._apply_guard_rails(report)
        return report

    def _apply_guard_rails(self, report: VerificationReport) -> None:
        """Downgrade verdicts that the evidence or the threshold contradicts.

        Args:
            report: The report to adjust in place.
        """
        threshold = self.settings.min_confidence
        auditor_verdict = report.verdict

        if report.verdict is Verdict.SUCCESS and report.confidence < threshold:
            report.verdict = Verdict.FAILED
            report.notes = _join_notes(
                report.notes,
                f"Downgraded to FAILED: the auditor's confidence "
                f"({report.confidence:.0%}) is below the required threshold "
                f"({threshold:.0%}).",
            )

        if report.verdict is Verdict.SUCCESS and not report.checks:
            report.verdict = Verdict.FAILED
            report.notes = _join_notes(
                report.notes,
                "Downgraded to FAILED: the auditor reported SUCCESS without any "
                "requirement-level checks, so the claim is unproven.",
            )

        unsatisfied = [check for check in report.checks if not check.status.is_satisfied]
        if report.verdict is Verdict.SUCCESS and unsatisfied:
            report.verdict = Verdict.FAILED
            report.notes = _join_notes(
                report.notes,
                "Downgraded to FAILED: the auditor reported SUCCESS while "
                f"{len(unsatisfied)} requirement(s) remained unsatisfied.",
            )

        if auditor_verdict is Verdict.FAILED and not report.checks:
            report.notes = _join_notes(
                report.notes,
                "The auditor returned no requirement-level checks; the verdict "
                "rests on its summary alone.",
            )


def _join_notes(existing: str, addition: str) -> str:
    """Append a note to an existing notes string.

    Args:
        existing: The current notes.
        addition: The note to append.

    Returns:
        The combined notes.
    """
    if not existing.strip():
        return addition
    return f"{existing.strip()}\n{addition}"


def parse_report_text(text: str) -> dict[str, Any]:
    """Extract the report payload from raw auditor output.

    Args:
        text: The auditor's raw text output.

    Returns:
        The decoded JSON payload.

    Raises:
        ResponseParseError: If no JSON object can be found or decoded.
    """
    if not text or not text.strip():
        raise ResponseParseError("The auditor returned an empty response.", snippet="")

    candidate = extract_json_object(text)
    if candidate is None:
        raise ResponseParseError(
            "The auditor's response did not contain a JSON object.",
            snippet=text[:400],
        )

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ResponseParseError(
            f"The auditor's response was not valid JSON: {exc.msg}",
            snippet=candidate[:400],
        ) from exc

    if not isinstance(payload, dict):
        raise ResponseParseError(
            "The auditor's response was a JSON value, not a JSON object.",
            snippet=candidate[:400],
        )
    return payload


def _coerce_confidence(value: Any) -> float:
    """Coerce an auditor-supplied confidence into the 0.0-1.0 range.

    Args:
        value: The raw value.

    Returns:
        A confidence score clamped to ``[0.0, 1.0]``.
    """
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score < 0.0:
        return 0.0
    if score > 1.0:
        # Tolerate percentages such as 85.
        if score <= 100.0:
            return score / 100.0
        return 1.0
    return score


def _coerce_str_list(value: Any) -> list[str]:
    """Coerce an auditor-supplied field into a list of strings.

    Args:
        value: The raw value.

    Returns:
        A list of non-empty strings.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def parse_report_payload(payload: dict[str, Any]) -> VerificationReport:
    """Validate an auditor payload and build a report from it.

    Args:
        payload: The decoded JSON payload.

    Returns:
        The parsed report.

    Raises:
        ResponseParseError: If the payload is missing the verdict field.
    """
    raw_verdict = str(payload.get("verdict", "")).strip().lower()
    if raw_verdict not in {Verdict.SUCCESS.value, Verdict.FAILED.value}:
        raise ResponseParseError(
            f"The auditor returned an invalid verdict: {payload.get('verdict')!r}. "
            "Expected 'success' or 'failed'.",
            snippet=str(payload.get("verdict"))[:200],
        )

    checks: list[VerificationCheck] = []
    raw_checks = payload.get("checks")
    if isinstance(raw_checks, list):
        for item in raw_checks:
            if not isinstance(item, dict):
                continue
            requirement = str(item.get("requirement", "")).strip()
            if not requirement:
                continue
            status = _coerce_status(item.get("status"))
            checks.append(
                VerificationCheck(
                    requirement=requirement,
                    status=status,
                    evidence=str(item.get("evidence", "")).strip(),
                    source=str(item.get("source", "")).strip(),
                )
            )

    return VerificationReport(
        verdict=Verdict(raw_verdict),
        confidence=_coerce_confidence(payload.get("confidence", 0.0)),
        summary=str(payload.get("summary", "")).strip(),
        checks=checks,
        discrepancies=_coerce_str_list(payload.get("discrepancies")),
        hallucinations=_coerce_str_list(payload.get("hallucinations")),
        missing_items=_coerce_str_list(payload.get("missing_items")),
        recommendations=_coerce_str_list(payload.get("recommendations")),
        notes=str(payload.get("notes", "")).strip(),
    )


def _coerce_status(value: Any) -> CheckStatus:
    """Coerce an auditor-supplied check status.

    Args:
        value: The raw value.

    Returns:
        The matching :class:`CheckStatus`; unknown values become
        ``UNVERIFIABLE``.
    """
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "pass": CheckStatus.VERIFIED,
        "passed": CheckStatus.VERIFIED,
        "success": CheckStatus.VERIFIED,
        "satisfied": CheckStatus.VERIFIED,
        "complete": CheckStatus.VERIFIED,
        "ok": CheckStatus.VERIFIED,
        "partially_verified": CheckStatus.PARTIAL,
        "incomplete": CheckStatus.PARTIAL,
        "fail": CheckStatus.FAILED,
        "not_done": CheckStatus.MISSING,
        "absent": CheckStatus.MISSING,
        "no_evidence": CheckStatus.UNVERIFIABLE,
        "unknown": CheckStatus.UNVERIFIABLE,
        "not_verifiable": CheckStatus.UNVERIFIABLE,
    }
    if text in aliases:
        return aliases[text]
    try:
        return CheckStatus(text)
    except ValueError:
        return CheckStatus.UNVERIFIABLE
