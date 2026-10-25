<div align="center">
  <img src="assets/logo.svg" alt="AgentProof" width="96" height="96">

  <h1>AgentProof</h1>

  <p><strong>Verify the agent's work against its claim.</strong></p>

  <p>
    An independent LLM auditor compares what an AI agent says it did with the
    files it produced, then fails the build when the proof is missing.
  </p>

  <p>
    <a href="#try-it-in-30-seconds-no-api-key">Try it in 30 seconds</a> ·
    <a href="#how-it-works">How it works</a> ·
    <a href="#a-separate-auditor">A separate auditor</a> ·
    <a href="#use-it-in-ci">CI</a> ·
    <a href="#configuration">Configuration</a>
  </p>

  <p>
    <a href="https://codeberg.org/0xPh0b0s/AgentProof"><img src="https://codeberg.org/0xPh0b0s/AgentProof/badges/stars.svg" alt="Codeberg stars"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e.svg" alt="MIT licensed"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-3776ab?logo=python&logoColor=white" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/typing-strict%20mypy-3b82f6.svg" alt="Strictly typed, mypy strict">
    <img src="https://img.shields.io/badge/runtime%20dependencies-4-brightgreen.svg" alt="Four runtime dependencies">
  </p>
</div>

---

## The problem

An agent finishes a task and reports success:

> *"I implemented the feature, added the migration, and ran the suite. All 42
> tests pass."*

You can trust that report, ask the same agent to check its work, or read every
file yourself. The first two repeat the agent's account. The third makes you
the QA department for every run.

AgentProof sends the task, the agent's claim, and the contents of the workspace
to a different model. The auditor must name the artifact that supports or
contradicts each requirement before it can return `SUCCESS`.

Without that evidence, the verdict is `FAILED` and the process exits `1`.

---

## Try it in 30 seconds (no API key)

```bash
pip install agentproof-cli
agentproof --demo
```

The demo runs artifact collection, prompt assembly, verdict parsing, guard
rails, and terminal rendering against a synthetic workspace and a pre-recorded
auditor answer. It reads nothing on your machine and needs no credentials:

```console
╭───────────────────────────────── Demo mode ──────────────────────────────────╮
│  A canned demonstration: a synthetic workspace and a pre-recorded auditor    │
│  answer. No API key is needed, and nothing on your machine is read.          │
╰──────────────────────────────────────────────────────────────────────────────╯

╭───────────────────────────────── AgentProof ─────────────────────────────────╮
│  Independent verification of an AI agent's claimed completion                │
╰──────────────────────────────────────────────────────────────────────────────╯

╭─────────────────────────────── Auditing with ────────────────────────────────╮
│  Provider            demo                                                    │
│  Model               agentproof-demo-auditor                                 │
│  Artifacts           5 files, 799 B                                          │
│  Threshold           75% confidence required for SUCCESS                     │
╰──────────────────────────────────────────────────────────────────────────────╯

╭──────────────────────────── Verification Result ─────────────────────────────╮
│                                                                              │
│   FAILED    Confidence ██████████████████████░░  91%                         │
│                                                                              │
│  The deployment script exists and the log records a clean pipeline run, but  │
│  the claimed 42 passing tests are not evidenced by any artifact.             │
│                                                                              │
│  1 verified  ·  2 unsatisfied  ·  3 requirement(s) checked                   │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

Evidence breakdown
  #  Status         Requirement                   Evidence
  1  VERIFIED       Create a deployment script    deploy.sh is present with a
                                                  working shebang and body.
                                                  deploy.sh
  2  PARTIAL        Run the test suite            run.log records 'pytest
                                                  finished' but no per-test
                                                  results.
                                                  run.log
  3  UNVERIFIABLE   Report exactly how many       No artifact contains a test
                    tests passed                  count or a pass/fail summary;
                                                  tests/test_deploy.py defines
                                                  only 3 test cases.
                                                  tests/test_deploy.py

╭─────────────────────────────── Discrepancies ────────────────────────────────╮
│  • The claim states 42 tests passed; the workspace contains 3 test cases     │
│  and no test count anywhere.                                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭──────────────────────────── Hallucinated claims ─────────────────────────────╮
│  • 'All 42 tests pass' has no supporting artifact.                           │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─────────────────────────────── Missing items ────────────────────────────────╮
│  • Test run output with per-test results                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─────────────────────────────── Recommendations ────────────────────────────────╮
│  • Save the full pytest output to the workspace before claiming success.     │
╰──────────────────────────────────────────────────────────────────────────────╯

╭─────────────────────────────── Auditor notes ────────────────────────────────╮
│  Confidence is limited because the workspace contains no test report.        │
│  Downgraded to FAILED: the auditor reported SUCCESS while 2 requirement(s)   │
│  remained unsatisfied.                                                       │
╰──────────────────────────────────────────────────────────────────────────────╯

auditor: demo · model: agentproof-demo-auditor · artifacts scanned: 5 · usage:
1349 tokens
```

The demo auditor reported `SUCCESS` with 91% confidence. AgentProof returned
`FAILED` because two requirements had no evidence. The guard rails downgrade a
confident verdict when evidence is missing.

---

## What you get

| | |
| --- | --- |
| 🧑‍⚖️ **An independent auditor** | A different model treats the claim as a hypothesis and looks for evidence in the workspace. |
| 📄 **Requirement-level evidence** | Every requirement the auditor extracted, its status, and the artifact that proves or disproves it. |
| 🧾 **Evidence completeness** | The collector records omitted files, truncated content, and exhausted budgets. The auditor and the report show those limits, so a collection gap cannot pass for absent work. |
| 🚦 **A binary verdict** | `SUCCESS` or `FAILED`, with no subjective score. |
| ⚖️ **Three guard rails** | A `SUCCESS` below your confidence threshold, without requirement-level checks, or with an unverified requirement becomes `FAILED`. |
| 🛡️ **Prompt-injection hardening** | Artifact content is labelled untrusted and framed with a random per-run nonce, so agent-authored text cannot instruct the auditor or forge a file boundary. |
| 🤝 **CI-native** | Exit codes `0` to `4` and a `--json` mode let an unproven claim block a merge. |
| 🧪 **Provider choice** | Anthropic and OpenAI out of the box, plus any OpenAI-compatible endpoint through `--base-url`. |

---

## Install

```bash
pip install agentproof-cli
```

The PyPI distribution is named **`agentproof-cli`**. It installs the
`agentproof` command and the `agentproof` import package.

Requires **Python 3.10+**. Four runtime dependencies: `click`, `rich`, `httpx`,
`python-dotenv`. Provide an API key for Anthropic or OpenAI.

From a checkout (use this until the first PyPI release):

```bash
git clone https://codeberg.org/0xPh0b0s/AgentProof.git
cd AgentProof
pip install -e ".[dev]"
```

---

## Quick start

### 1. Describe the task

```bash
agentproof init
```

The wizard asks for the task definition, the agent's claim, the workspace, and
the auditor. It writes `.agentproof.json`:

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

Prefer the command line? Everything is overridable:

```bash
agentproof --check \
  --task "Create a deployment script and run the test suite." \
  --claim "I created deploy.sh and all 42 tests pass." \
  --workspace ./workspace
```

### 2. Provide credentials

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY=sk-...
```

AgentProof loads a `.env` file from the project root or any parent directory,
so the key does not need to appear in your shell history:

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
```

### 3. Verify

```bash
agentproof --check
```

---

## How it works

```
   ┌────────────┐   task + claim   ┌────────────────┐
   │   Agent    │ ───────────────▶ │                │
   │  (claimed) │                  │   AgentProof   │
   └────────────┘                  │                │
                                   │  1. collect    │
   ┌────────────┐  file contents   │  2. prompt     │
   │ Workspace  │ ───────────────▶ │  3. audit      │
   │ (evidence) │                  │  4. guard      │
   └────────────┘                  │  5. report     │
                                   └────────┬───────┘
                                            │
                                    ┌───────▼───────┐
                                    │  Independent  │
                                    │    auditor    │
                                    │  (a model)    │
                                    └───────────────┘
```

1. **Context gathering.** The task, the claim, and the workspace are resolved
   from, in order of precedence: command-line options, environment variables,
   `.agentproof.json`, `~/.config/agentproof/config.json`, built-in defaults.
   Anything still missing is asked for interactively.

2. **Artifact collection.** The collector walks the workspace and reads each
   relevant file. It follows `.gitignore`, skips virtualenvs and caches, marks
   binaries as non-inspectable, and applies per-file, per-total, and per-count
   budgets to keep the prompt bounded. The completeness note records omitted
   files, truncated content, and exhausted budgets so the auditor can tell a
   collection limit from absent work.

3. **Independent audit.** The task, the claim, and the artifact contents go to
   a *separate* model with a prompt that treats the claim as a hypothesis. The
   auditor must decompose the task into requirements and cite evidence for
   each one. Artifact content is marked as untrusted data, and each file is
   framed with a random per-run nonce, so agent-authored text cannot instruct
   the auditor or forge a file boundary.

4. **Structured verdict.** The auditor answers with a JSON report: a verdict, a
   confidence score, a per-requirement checklist with evidence and source
   paths, and lists of discrepancies, hallucinations, missing items, and
   recommendations.

5. **Guard rails.** Three rules override the auditor's verdict:
   - a `SUCCESS` whose confidence is below `--min-confidence` becomes `FAILED`;
   - a `SUCCESS` with no requirement-level checks becomes `FAILED`;
   - a `SUCCESS` containing any non-`verified` requirement becomes `FAILED`.

   A claim needs complete, cited evidence to pass.

6. **Reporting.** A coloured terminal report with a status badge, confidence
   bar, requirement-by-requirement evidence table, and discrepancy lists. Use
   `--json` for CI. When the collector omitted or truncated evidence, the
   report records that limit instead of letting a `FAILED` verdict hide it.

---

## A separate auditor

| | Ask the agent | Ask the agent to check its own work | **AgentProof** |
| --- | --- | --- | --- |
| Who audits? | The agent that did the work | The agent that did the work | **A separate model** |
| Reads the artifacts? | Usually not | Sometimes | **All collected files** |
| Adversarial? | No | No | **Yes; it is told to look for gaps** |
| Burden of proof | On you | On the agent | **On the agent** |
| Machine-checkable? | No | No | **Yes; exit code and JSON** |
| Works in CI? | No | No | **Yes** |

The agent that did the work has already written the account it wants you to
accept. A separate model reads the workspace without the agent's incentive to
defend that summary. The auditor does not share the agent's stake in the
outcome.

---

## Use cases

- **CI gate for agent-generated changes.** Block the merge when an agent's
  summary is not backed by files. A non-zero exit code and a JSON report give
  the pipeline a clear signal.
- **A second pair of eyes before you read the diff.** Get a
  requirement-by-requirement breakdown of what landed and what the summary
  left out.
- **Agent harness integration.** Score a run, feed the verdict back into the
  loop, and let the agent retry with the missing-item list in hand.
- **Audit trail.** A machine-readable record of what was delivered when it was
  delivered.
- **Regression testing for agent prompts.** Measure whether a prompt change
  produced more accurate work or more persuasive prose.

---

## Command reference

| Command | Purpose |
| --- | --- |
| `agentproof --check` | Run the full verification workflow. |
| `agentproof` | Same as `--check` (the default action). |
| `agentproof --demo` | Self-contained demonstration. No API key, no network. |
| `agentproof init` | Interactive setup wizard that writes `.agentproof.json`. |
| `agentproof doctor` | Diagnose configuration, credentials, and resolved settings. |

### Common options

| Option | Description |
| --- | --- |
| `--demo` | Run the self-contained demonstration. No API key, no network. |
| `--task TEXT` / `--task-file PATH` | The task definition given to the agent. |
| `--claim TEXT` / `--claim-file PATH` | The agent's claim of what it did. |
| `--workspace PATH` | Directory (or file) holding the agent's output. |
| `--artifact PATH` | Extra log or output file to inspect (repeatable). |
| `--provider NAME` | `anthropic` or `openai`. |
| `--model NAME` | Model used as the auditor. |
| `--base-url URL` | Override the API base URL (local models, gateways). |
| `--min-confidence FLOAT` | Minimum confidence required for a `SUCCESS` verdict. |
| `--include GLOB` / `--exclude GLOB` | Restrict or veto collected files. |
| `--auditor-instructions TEXT` | Extra domain context for the auditor. |
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

---

## Configuration

### Configuration files

AgentProof looks for `.agentproof.json` in the current directory and every
parent directory, and for `~/.config/agentproof/config.json`. A `.env` file is
loaded from the current directory and every parent directory.

A complete sample lives in
[`examples/agentproof.example.json`](examples/agentproof.example.json). Copy it
to `.agentproof.json` and edit it, or run `agentproof init` to be walked through
the same fields.

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `task` | string | none | The task definition given to the agent. |
| `claim` | string | none | The agent's claim of what it accomplished. |
| `task_file` | path | none | File containing the task definition. |
| `claim_file` | path | none | File containing the agent's claim. |
| `workspace` | path | `.` | Directory (or file) with the agent's output. |
| `artifacts` | list | `[]` | Extra files or directories to inspect. |
| `provider` | string | `anthropic` | `anthropic` or `openai`. |
| `model` | string | provider default | Model used as the auditor. |
| `base_url` | string | provider default | Override the API base URL. |
| `api_key` | string | none | API key. Prefer the environment variable. |
| `api_key_env` | string | none | Name of an environment variable holding the key. |
| `min_confidence` | float | `0.75` | Minimum confidence for a `SUCCESS` verdict. |
| `max_files` | int | `200` | Maximum number of artifacts. |
| `max_artifact_bytes` | int | `120000` | Maximum bytes read per artifact. |
| `max_total_bytes` | int | `1500000` | Maximum bytes read in total. |
| `include` | list | `[]` | Globs restricting which files are collected. |
| `exclude` | list | `[]` | Globs vetoing files from the collection. |
| `auditor_instructions` | string | none | Extra domain context for the auditor. |
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

## Use it in CI

```yaml
# .forgejo/workflows/verify-agent.yml
name: Verify agent claim
on: [workflow_dispatch, pull_request]

jobs:
  proof:
    runs-on: docker
    container:
      image: python:3.12
    steps:
      - uses: https://codeberg.org/actions/checkout@v4
      - run: pip install agentproof-cli
      - run: agentproof --check --json > proof.json
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - uses: https://codeberg.org/actions/upload-artifact@v4
        with:
          name: agent-proof
          path: proof.json
```

A non-zero exit code fails the job, so an unproven claim blocks the pipeline.

To put the report in a PR comment, pipe it through
[`jq`](https://jqlang.github.io/jq/). The JSON schema is stable.

---

## Use it as a library

```python
from pathlib import Path

from agentproof import Settings, build_context
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
try:
    report = Verifier(provider, settings).verify(context)
finally:
    provider.close()

print(report.verdict.label, report.confidence)
for check in report.checks:
    print(check.status.value, check.requirement)
```

---

## FAQ

**Which models can be the auditor?**
Anthropic (default `claude-sonnet-5-5`) and OpenAI (default `gpt-6.1-sol`) are
supported out of the box, and `--model` accepts any model your provider
exposes.

**Can I use a local model?**
Yes. Point `--base-url` at any OpenAI-compatible endpoint: Ollama, vLLM,
LM Studio, or an internal gateway. Local servers ignore credentials, but
AgentProof requires a non-empty key. Use any dummy value:

```bash
export OPENAI_API_KEY=ollama        # any non-empty value will do
agentproof --check --provider openai \
  --base-url http://localhost:11434 --model qwen3
```

**Does it send my code to a third party?**
Yes. It sends collected artifacts to the provider you configure. Use
`--include` or `--exclude` to control what leaves your machine, or point
`--base-url` at a local server.

**What if the agent did not write the files?**
A missing artifact is evidence of a missing requirement. The audit fails.

**Is the auditor itself trustworthy?**
Models make mistakes. AgentProof shows the evidence for every requirement, and
the guard rails assume the auditor may be over-confident. Check the evidence
table along with the verdict.

**Does this replace tests?**
No. Tests verify behaviour. AgentProof verifies that the claimed work exists.
They cover different failure modes.

---

## Development

```bash
pip install -e ".[dev]"

pytest                      # 133 tests
ruff check .                # lint
ruff format --check .       # formatting
mypy                        # strict type checking
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
├── demo.py         # The self-contained `--demo` mode
├── models.py       # Typed data models
├── errors.py       # Exception hierarchy
├── utils.py        # Glob matching, gitignore rules, JSON extraction
└── providers/      # Anthropic and OpenAI backends behind one interface
```

### CI and releasing

Lint, type-checking and the test suite run on
[Codeberg Actions](https://codeberg.org/0xPh0b0s/AgentProof/actions) via
`.forgejo/workflows/ci.yml`. Actions must be enabled once in the repository
settings (**Settings → Repository → Advanced → Enable Actions**).

Publishing is handled by `.forgejo/workflows/release.yml`; it needs a
`PYPI_API_TOKEN` repository secret. To publish by hand:

```bash
python -m build
python -m twine upload dist/*
```

Once the first release is on PyPI, add these two badges to the header:

```html
<a href="https://pypi.org/project/agentproof-cli/"><img src="https://img.shields.io/pypi/v/agentproof-cli.svg" alt="Latest PyPI release"></a>
<a href="https://codeberg.org/0xPh0b0s/AgentProof/actions/workflows/ci.yml"><img src="https://codeberg.org/0xPh0b0s/AgentProof/badges/workflows/ci.yml/badge.svg" alt="CI status"></a>
```

---

## Contributing

Contributions are welcome: bug reports, provider backends, prompt
improvements, and new guard-rail rules.

1. Open an issue that describes the problem, so we can agree on the approach.
2. Fork the repository and create a branch.
3. Run `ruff check .`, `ruff format --check .`, `mypy`, and `pytest` before
   opening the pull request.
4. Add a test for every behaviour change.
5. Open a pull request describing what changed and why.

New providers are welcome: implement `agentproof.providers.base.Provider` and
register it in `agentproof/providers/registry.py`.

---

## License

MIT. See [LICENSE](LICENSE).

Changelog: [CHANGELOG.md](CHANGELOG.md).
