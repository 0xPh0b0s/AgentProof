<div align="center">
  <img src="assets/logo.svg" alt="AgentProof" width="96" height="96">

  <h1>AgentProof</h1>

  <p><strong>Don't trust the agent's report card. Verify it.</strong></p>

  <p>
    An independent LLM auditor checks what an AI agent <em>claims</em> it did
    against the files it <em>actually</em> produced — and fails the build when
    the proof is missing.
  </p>

  <p>
    <a href="#try-it-in-30-seconds-no-api-key">Try it in 30 seconds</a> ·
    <a href="#how-it-works">How it works</a> ·
    <a href="#why-not-just-ask-the-agent">Why not just ask the agent?</a> ·
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

Your agent says it finished the job.

> *"I implemented the feature, added the migration, and ran the suite — all 42
> tests pass."*

Now what? You have three options, and all of them are bad:

1. **Trust it.** It is a machine grading its own homework.
2. **Ask it again.** It already gave you the answer it wanted you to hear.
3. **Read everything by hand.** Sure — but now you are the QA department for
   every agent run, forever.

AgentProof is the fourth option: **ask a different model.** A separate auditor
gets the original task, the agent's final claim, and the *actual contents* of
the workspace — then has to name the artifact that proves or disproves every
requirement before it is allowed to say `SUCCESS`.

If the proof isn't there, the verdict is `FAILED` and the process exits `1`.

---

## Try it in 30 seconds (no API key)

```bash
pip install agentproof-cli
agentproof --demo
```

The demo runs the **real** pipeline — artifact collection, prompt assembly,
verdict parsing, guard rails, terminal rendering — against a synthetic
workspace and a pre-recorded auditor answer. It reads nothing on your machine
and needs no credentials:

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

Look at the **Auditor notes** panel: the demo's auditor was *confident* and said
`SUCCESS`. AgentProof still returned `FAILED`, because two requirements were
never evidenced. That guard rail is the whole point of the tool.

---

## What you get

| | |
| --- | --- |
| 🧑‍⚖️ **An independent auditor** | A different model, with the claim treated as a hypothesis to be tested — never as evidence for itself. |
| 📄 **Requirement-level evidence** | Every requirement the auditor extracted, its status, and the artifact that proves or disproves it. |
| 🚦 **A binary verdict** | `SUCCESS` or `FAILED`. No "looks good to me", no 7/10 confidence vibes. |
| ⚖️ **Two guard rails** | A `SUCCESS` below your confidence threshold, or with any unverified requirement, is downgraded to `FAILED`. |
| 🛡️ **Prompt-injection hardening** | Artifact content is explicitly labelled untrusted data so agent-authored files cannot instruct the auditor. |
| 🤝 **CI-native** | Exit codes `0`–`4` and a `--json` mode, so an unproven claim can block a merge. |
| 🧪 **Zero vendor lock-in** | Anthropic and OpenAI out of the box; any OpenAI-compatible endpoint via `--base-url`. |

---

## Install

```bash
pip install agentproof-cli
```

The PyPI distribution is named **`agentproof-cli`** — it installs the
`agentproof` command and the `agentproof` import package.

Requires **Python 3.10+**. Four runtime dependencies: `click`, `rich`, `httpx`,
`python-dotenv`. Bring your own API key for the auditor — Anthropic or OpenAI.

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
the auditor — then writes `.agentproof.json`:

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

A `.env` file in the project root (or any parent) is loaded automatically, so
the key never has to touch your shell history:

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

2. **Artifact collection.** The workspace is walked and every relevant file is
   read — content, not just filenames. `.gitignore` is honoured, virtualenvs
   and caches are skipped, binaries are flagged as non-inspectable, and
   per-file / per-total / per-count budgets keep the prompt bounded.

3. **Independent audit.** The task, the claim, and the artifact contents go to
   a *separate* model with a prompt that treats the claim as a hypothesis. The
   auditor must decompose the task into requirements and cite evidence for
   each one. Artifact content is explicitly marked as untrusted data so that
   agent-authored text cannot instruct the auditor.

4. **Structured verdict.** The auditor answers with a JSON report: a verdict, a
   confidence score, a per-requirement checklist with evidence and source
   paths, and lists of discrepancies, hallucinations, missing items, and
   recommendations.

5. **Guard rails.** Two rules override the auditor's own verdict:
   - a `SUCCESS` whose confidence is below `--min-confidence` → `FAILED`;
   - a `SUCCESS` containing any non-`verified` requirement → `FAILED`.

   The burden of proof is on the agent: anything short of complete, evidenced
   success is a failure.

6. **Reporting.** A coloured terminal report with a status badge, a confidence
   bar, the requirement-by-requirement evidence table, and the discrepancy
   lists — or a JSON document for CI.

---

## Why not just ask the agent?

| | Ask the agent | Ask the agent to check its own work | **AgentProof** |
| --- | --- | --- | --- |
| Who audits? | The agent that did the work | The agent that did the work | **A separate model** |
| Reads the artifacts? | Usually not | Sometimes | **Always, in full** |
| Adversarial? | No | No | **Yes — it is told to look for holes** |
| Burden of proof | On you | On the agent | **On the agent** |
| Machine-checkable? | No | No | **Yes — exit code + JSON** |
| Works in CI? | No | No | **Yes** |

An agent asked to review its own work is being asked to be its own worst enemy.
It has every incentive to declare victory, and it has already composed the
story it is most likely to repeat. AgentProof removes the agent from the
auditing seat entirely.

---

## Use cases

- **CI gate for agent-generated changes.** Block the merge when an agent's
  summary is not backed by files. Non-zero exit code, JSON artefact, done.
- **A second pair of eyes before you read the diff.** Get a
  requirement-by-requirement breakdown of what landed and what was quietly
  skipped.
- **Agent harness integration.** Score a run, feed the verdict back into the
  loop, and let the agent retry with the missing-item list in hand.
- **Audit trail.** A machine-readable proof of what was actually delivered, at
  the moment it was delivered.
- **Regression testing for agent prompts.** Did your prompt change make the
  agent more honest, or did it just make the agent more articulate?

---

## Command reference

| Command | Purpose |
| --- | --- |
| `agentproof --check` | Run the full verification workflow. |
| `agentproof` | Same as `--check` (the default action). |
| `agentproof --demo` | Self-contained demonstration. No API key, no network. |
| `agentproof init` | Interactive setup wizard that writes `.agentproof.json`. |
| `agentproof doctor` | Diagnose configuration, credentials, and resolved settings. |

### Frequently used options

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

A fully populated sample lives in
[`examples/agentproof.example.json`](examples/agentproof.example.json) — copy
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

Want the report in the PR comment instead of a raw file? Pipe it through
[`jq`](https://jqlang.github.io/jq/) and post it wherever you like — the JSON
schema is stable.

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
Yes. Point `--base-url` at any OpenAI-compatible endpoint — Ollama, vLLM,
LM Studio, an internal gateway. Local servers ignore the credentials, but
AgentProof still needs a non-empty key to be present, so give it a dummy one:

```bash
export OPENAI_API_KEY=ollama        # any non-empty value will do
agentproof --check --provider openai \
  --base-url http://localhost:11434 --model qwen3
```

**Does it send my code to a third party?**
Yes — the artifacts it collects are sent to whichever provider you configure.
Control exactly what leaves your machine with `--include` / `--exclude`, or
keep it all local with a local `--base-url`.

**What if the agent never wrote the files?**
Then there is nothing to verify, and that is exactly the finding. A missing
artifact is evidence of a missing requirement, not a technicality to route
around.

**Is the auditor itself trustworthy?**
No model is. That is why AgentProof shows you the *evidence* for every
requirement, not just the verdict, and why the guard rails assume the auditor
is over-confident. Read the table; do not just read the badge.

**Does this replace tests?**
No, and it is not trying to. Tests verify behaviour; AgentProof verifies that
the work exists at all. The two compose well.

---

## Development

```bash
pip install -e ".[dev]"

pytest                      # 110 tests
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

Contributions are welcome — bug reports, a new provider backend, a better
auditor prompt, or a rule you think the guard rails should enforce.

1. Open an issue describing the problem before you start, so we can agree on
   the approach.
2. Fork the repository and create a branch.
3. Keep the bar high: `ruff check .`, `ruff format --check .`, `mypy` and
   `pytest` all have to pass.
4. Add a test for every behaviour change.
5. Open a pull request describing what changed and why.

New providers are welcome: implement `agentproof.providers.base.Provider` and
register it in `agentproof/providers/registry.py`.

---

## License

MIT — see [LICENSE](LICENSE).

Changelog: [CHANGELOG.md](CHANGELOG.md).
