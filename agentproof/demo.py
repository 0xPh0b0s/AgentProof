"""A self-contained demonstration of the AgentProof pipeline.

The demo exists so that a curious visitor can see exactly what the tool does
within thirty seconds, without an API key and without touching their own
files. It runs the *real* pipeline - artifact collection, prompt assembly,
verdict parsing, guard rails and terminal rendering - against a small
synthetic workspace, and swaps the LLM call for a canned auditor answer.

The workspace is written to a temporary directory and removed again, so the
demo never leaves anything behind.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from agentproof.config import Settings
from agentproof.models import Usage
from agentproof.providers.base import LLMResponse, Provider, ProviderSpec

__all__ = [
    "DEMO_CLAIM",
    "DEMO_FILES",
    "DEMO_TASK",
    "DemoProvider",
    "demo_settings",
    "demo_workspace",
]


#: The task handed to the fictional agent.
DEMO_TASK = (
    "Create a deployment script (deploy.sh) and run the test suite. "
    "Report exactly how many tests passed."
)

#: The claim the fictional agent made about that task.
DEMO_CLAIM = "I created deploy.sh and all 42 tests pass."

#: The identifier reported as the auditor for the demo run.
DEMO_MODEL = "agentproof-demo-auditor"

#: Files written into the temporary demo workspace.
DEMO_FILES: dict[str, str] = {
    "deploy.sh": """\
#!/usr/bin/env bash
# Deploy the built application to the target host.
set -euo pipefail

TARGET="${1:-/srv/app}"
echo "deploying release $(cat VERSION) to ${TARGET}"
rsync -a --delete build/ "${TARGET}/"
systemctl restart app.service
echo "deploy ok"
""",
    "VERSION": "1.4.2\n",
    "run.log": """\
2026-10-21 09:12:03 INFO  starting deployment pipeline
2026-10-21 09:12:04 INFO  build finished
2026-10-21 09:12:07 INFO  pytest finished
2026-10-21 09:12:09 INFO  deploy ok
""",
    "tests/test_deploy.py": '''\
"""Tests for the deployment script."""


def test_script_exists():
    assert True


def test_script_is_executable():
    assert True


def test_version_matches_release():
    assert True
''',
    "NOTES.md": """\
# Deployment notes

- deploy.sh is in place and has been run against staging.
- The test suite was executed as part of the pipeline.
- All 42 tests pass, so the release is green.
""",
}


#: The canned auditor answer used by the demo.
#:
#: It deliberately reports ``success`` with high confidence while leaving two
#: requirements unsatisfied, so that the demo also shows the guard rails
#: downgrading an over-confident verdict to ``failed``.
DEMO_RESPONSE: dict[str, Any] = {
    "verdict": "success",
    "confidence": 0.91,
    "summary": (
        "The deployment script exists and the log records a clean pipeline run, but the "
        "claimed 42 passing tests are not evidenced by any artifact."
    ),
    "checks": [
        {
            "requirement": "Create a deployment script",
            "status": "verified",
            "evidence": "deploy.sh is present with a working shebang and body.",
            "source": "deploy.sh",
        },
        {
            "requirement": "Run the test suite",
            "status": "partial",
            "evidence": "run.log records 'pytest finished' but no per-test results.",
            "source": "run.log",
        },
        {
            "requirement": "Report exactly how many tests passed",
            "status": "unverifiable",
            "evidence": (
                "No artifact contains a test count or a pass/fail summary; "
                "tests/test_deploy.py defines only 3 test cases."
            ),
            "source": "tests/test_deploy.py",
        },
    ],
    "discrepancies": [
        "The claim states 42 tests passed; the workspace contains 3 test cases and no "
        "test count anywhere.",
    ],
    "hallucinations": [
        "'All 42 tests pass' has no supporting artifact.",
    ],
    "missing_items": [
        "Test run output with per-test results",
    ],
    "recommendations": [
        "Save the full pytest output to the workspace before claiming success.",
    ],
    "notes": "Confidence is limited because the workspace contains no test report.",
}


class DemoProvider(Provider):
    """A provider that replays a canned auditor answer.

    It implements the same interface as the real providers, so the demo
    exercises the genuine verification code path instead of a shortcut.

    Attributes:
        spec: Static metadata describing the demo auditor.
    """

    spec = ProviderSpec(
        name="demo",
        env_var="AGENTPROOF_DEMO",
        default_model=DEMO_MODEL,
        default_base_url="local://demo",
        label="Built-in demo auditor",
    )

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 8192,
        temperature: float | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Return the canned audit report.

        Args:
            system: The auditor system prompt. Unused.
            user: The auditor user prompt. Unused.
            max_tokens: Maximum tokens to generate. Unused.
            temperature: Sampling temperature. Unused.
            json_schema: Optional JSON schema. Unused.

        Returns:
            A response holding the canned JSON payload.
        """
        prompt_chars = len(system) + len(user)
        prompt_tokens = prompt_chars // 4
        return LLMResponse(
            text=json.dumps(DEMO_RESPONSE, indent=2),
            model=self.spec.default_model,
            provider=self.spec.name,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=len(json.dumps(DEMO_RESPONSE)) // 4,
            ),
        )


@contextmanager
def demo_workspace() -> Iterator[Path]:
    """Create a temporary workspace holding the demo artifacts.

    Yields:
        The path of the temporary workspace.

    The directory and everything inside it are deleted on exit.
    """
    with tempfile.TemporaryDirectory(prefix="agentproof-demo-") as tmp:
        root = Path(tmp)
        for name, content in DEMO_FILES.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        (root / "deploy.sh").chmod(0o755)
        yield root


def demo_settings(workspace: Path) -> Settings:
    """Build the settings used for a demo run.

    Args:
        workspace: Path of the temporary demo workspace.

    Returns:
        Settings pointing at the demo workspace and auditor.
    """
    return Settings(
        task=DEMO_TASK,
        claim=DEMO_CLAIM,
        workspace=workspace,
        provider="demo",
        model=DEMO_MODEL,
        min_confidence=0.75,
    )
