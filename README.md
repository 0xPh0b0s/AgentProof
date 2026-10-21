# AgentProof

**Independent verification that an AI agent actually did what it claimed to do.**

Agents are good at describing work they did not do. AgentProof takes a task
definition, an agent's final claim, and the artifacts the agent produced, then
asks an independent LLM auditor to check the claim against the evidence. The
result is a binary verdict, a confidence score, and a requirement-by-requirement
breakdown of what was verified and what was not.

```
╭───────────────────────────────── AgentProof ─────────────────────────────────╮
│  Independent verification of an AI agent's claimed completion                │
╰──────────────────────────────────────────────────────────────────────────────╯

╭──────────────────────────── Verification Result ─────────────────────────────╮
│                                                                              │
│   FAILED    Confidence ██████████████████████░░  91%                         │
│                                                                              │
│  The deployment script exists and the log records a clean test run, but the  │
│  claimed 42 passing tests are not evidenced by any artifact.                 │
│                                                                              │
│  1 verified  ·  2 unsatisfied  ·  3 requirement(s) checked                   │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

Evidence breakdown
  #  Status         Requirement                 Evidence
  1  VERIFIED       Create a deployment script  deploy.sh is present with a
                                                working shebang and body.
                                                deploy.sh
  2  PARTIAL        Run the test suite          run.log records 'pytest
                                                finished' but no per-test
                                                results.
                                                run.log
  3  UNVERIFIABLE   All 42 tests pass           No artifact contains a test
                                                count or a pass/fail summary.
```

---

## Installation

AgentProof requires **Python 3.10+**.

```bash
# with pip
pip install agentproof

# or from a checkout, with poetry
poetry install

# or from a checkout, with pip
pip install -e ".[dev]"
```

This installs the `agentproof` command.

---

## Quick start

### 1. Describe the task

Either answer the interactive prompts:

```bash
agentproof --check
```

...or create a configuration file once and reuse it:

```bash
agentproof init
```

The wizard asks for the task definition, the agent's claim, the workspace, the
auditor provider and model, and writes `.agentproof.json`:

```json
{
  "task": "Create a deployment script and run the test suite.",
  "claim": "I created deploy.sh and all 42 tests pass.",
  "workspace": "./workspace",
  "provider": "anthropic",
  "model": "claude-sonnet-5-5",
  "min_confidence": 0.75
}
```

### 2. Provide credentials

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY=sk-...
```

A `.env` file in the project root (or any parent directory) is loaded
automatically, so you can keep the key out of your shell history:

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
```

### 3. Verify

```bash
agentproof --check
```

---

## Command reference

| Command | Purpose |
| --- | --- |
| `agentproof --check` | Run the full verification workflow. |
| `agentproof` | Same as `--check` (the default action). |
| `agentproof init` | Interactive setup wizard that writes `.agentproof.json`. |
| `agentproof doctor` | Diagnose configuration, credentials, and resolved settings. |

### Frequently used options

| Option | Description |
| --- | --- |
| `--task TEXT` / `--task-file PATH` | The task definition given to the agent. |
| `--claim TEXT` / `--claim-file PATH` | The agent's claim of what it did. |
| `--workspace PATH` | Directory (or file) holding the agent's output. |
| `--artifact PATH` | Extra log or output file to inspect (repeatable). |
| `--provider NAME` | `anthropic` or `openai`. |
| `--model NAME` | Model used as the auditor. |
| `--min-confidence FLOAT` | Minimum confidence required for a SUCCESS verdict. |
| `--include GLOB` / `--exclude GLOB` | Restrict or veto collected files. |
| `--json` | Emit the report as JSON (for CI). |
| `--dry-run` | Print the auditor prompt without calling the API. |
| `--quiet` / `-q` | Print only the verdict line. |
| `--config PATH` | Use a specific configuration file. |
| `--no-color` | Disable coloured output. |

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The claim was verified: verdict `SUCCESS`. |
| `1` | The claim was not verified: verdict `FAILED`. |
| `2` | Configuration or usage error (missing task, credentials, workspace...). |
| `3` | The LLM provider request failed. |
| `4` | The auditor's answer could not be parsed. |

This makes the tool usable directly as a CI gate:

```bash
agentproof --check --json > proof.json || exit 1
```

---

## How the verification works

1. **Context gathering.** AgentProof resolves the task definition, the agent's
   claim, and the workspace. Values come from, in order of precedence: command
   line options, environment variables, `.agentproof.json`, the user-wide
   `~/.config/agentproof/config.json`, and built-in defaults. Anything still
   missing is asked for interactively.

2. **Artifact collection.** The workspace is walked and every relevant file is
   read. `.gitignore` files are honoured, virtualenvs and caches are skipped,
   binary files are reported as non-inspectable, and per-file, per-total and
   per-file-count budgets keep the prompt bounded.

3. **Independent audit.** The task, the claim, and the artifact contents are
   handed to a *separate* auditor model (Claude or GPT) with a prompt that
   treats the claim as a hypothesis rather than as evidence. Artifact content is
   explicitly marked as untrusted data so that agent-authored text cannot
   instruct the auditor.

4. **Structured verdict.** The auditor returns a JSON report: a verdict, a
   confidence score, a per-requirement checklist with evidence, and lists of
   discrepancies, hallucinations, missing items, and recommendations.

5. **Guard rails.** Two rules can override the auditor's own verdict:
   - a `SUCCESS` verdict whose confidence is below `--min-confidence` is
     downgraded to `FAILED`;
   - a `SUCCESS` verdict that contains any non-`verified` requirement is
     downgraded to `FAILED`.

   The burden of proof is on the agent: anything short of complete, evidenced
   success is a failure.

6. **Reporting.** A coloured terminal report with a status badge, a confidence
   bar, the requirement-by-requirement evidence table, and the discrepancy
   lists - or a JSON document for CI.

---

## Configuration reference

### Configuration files

AgentProof looks for `.agentproof.json` in the current directory and every
parent directory, and for `~/.config/agentproof/config.json`. A `.env` file is
loaded from the current directory and every parent directory.

A fully populated sample lives in
[`examples/agentproof.example.json`](examples/agentproof.example.json) - copy
it to `.agentproof.json` and edit it, or run `agentproof init` to be walked
through the same fields interactively.

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `task` | string | — | The task definition given to the agent. |
| `claim` | string | — | The agent's claim of what it accomplished. |
| `task_file` | path | — | File containing the task definition. |
| `claim_file` | path | — | File containing the agent's claim. |
| `workspace` | path | `.` | Directory (or file) with the agent's output. |
| `artifacts` | list | `[]` | Extra files or directories to inspect. |
| `provider` | string | `anthropic` | `anthropic` or `openai`. |
| `model` | string | provider default | Model used as the auditor. |
| `base_url` | string | provider default | Override the API base URL. |
| `api_key` | string | — | API key. Prefer the environment variable. |
| `api_key_env` | string | — | Name of an environment variable holding the key. |
| `min_confidence` | float | `0.75` | Minimum confidence for a `SUCCESS` verdict. |
| `max_files` | int | `200` | Maximum number of artifacts. |
| `max_artifact_bytes` | int | `120000` | Maximum bytes read per artifact. |
| `max_total_bytes` | int | `1500000` | Maximum bytes read in total. |
| `include` | list | `[]` | Globs restricting which files are collected. |
| `exclude` | list | `[]` | Globs vetoing files from the collection. |
| `auditor_instructions` | string | — | Extra domain context for the auditor. |
| `temperature` | float | provider default | Sampling temperature. |
| `timeout` | float | `120` | API timeout in seconds. |
| `max_retries` | int | `3` | Retries for transient API failures. |
| `max_tokens` | int | `8192` | Maximum tokens the auditor may generate. |

### Environment variables

| Variable | Effect |
| --- | --- |
| `ANTHROPIC_API_KEY` | API key for the Anthropic provider. |
| `OPENAI_API_KEY` | API key for the OpenAI provider. |
| `AGENTPROOF_PROVIDER` | Override the provider. |
| `AGENTPROOF_MODEL` | Override the model. |
| `AGENTPROOF_BASE_URL` | Override the API base URL. |
| `AGENTPROOF_TASK` / `AGENTPROOF_CLAIM` | Override the task / claim. |
| `AGENTPROOF_WORKSPACE` | Override the workspace. |
| `AGENTPROOF_MIN_CONFIDENCE` | Override the confidence threshold. |
| `AGENTPROOF_MAX_FILES` | Override the artifact count budget. |
| `AGENTPROOF_AUDITOR_INSTRUCTIONS` | Extra domain context for the auditor. |

---

## CI usage

```yaml
# .github/workflows/verify-agent.yml
name: Verify agent claim
on: [workflow_dispatch]

jobs:
  proof:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install agentproof
      - run: agentproof --check --json > proof.json
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - uses: actions/upload-artifact@v4
        with:
          name: agent-proof
          path: proof.json
```

A non-zero exit code fails the job, so an unproven claim blocks the pipeline.

---

## Using AgentProof as a library

```python
from pathlib import Path

from agentproof import build_context, Settings
from agentproof.providers.registry import create_provider
from agentproof.verifier import Verifier

settings = Settings(
    task="Create a deployment script and run the test suite.",
    claim="I created deploy.sh and all 42 tests pass.",
    workspace=Path("./workspace"),
    provider="anthropic",
    model="claude-sonnet-5-5",
)

context = build_context(settings)
provider = create_provider(provider=settings.provider, api_key=None)
report = Verifier(provider, settings).verify(context)

print(report.verdict.label, report.confidence)
for check in report.checks:
    print(check.status.value, check.requirement)
```

---

## Development

```bash
poetry install          # or: pip install -e ".[dev]"
poetry run pytest       # or: pytest
poetry run ruff check .
poetry run mypy
poetry run ruff format .
```

### Project layout

```
agentproof/
├── cli.py          # Click command-line interface
├── config.py       # Layered configuration discovery and merging
├── context.py      # Assembles the verification context
├── artifacts.py    # Workspace scanning and artifact collection
├── prompts.py      # Auditor prompts and the report JSON schema
├── verifier.py     # The verification engine and its guard rails
├── report.py       # Terminal and JSON reporting
├── wizard.py       # Interactive setup wizard
├── models.py       # Typed data models
├── errors.py       # Exception hierarchy
├── utils.py        # Glob matching, gitignore rules, JSON extraction
└── providers/      # Anthropic and OpenAI backends behind one interface
```

---

## License

MIT - see [LICENSE](LICENSE).
