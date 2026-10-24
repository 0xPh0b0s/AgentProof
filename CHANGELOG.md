# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-21

### Added

- Packaged for PyPI as `agentproof-cli`; the installed command and the import
  package are both named `agentproof`.
- `agentproof --check`: the full verification workflow — context gathering,
  artifact collection, independent audit, guard rails, and terminal reporting.
- `agentproof init`: an interactive wizard that writes `.agentproof.json`.
- `agentproof doctor`: diagnostics for configuration, credentials, and
  resolved settings.
- `agentproof --demo`: a self-contained demonstration of the pipeline that
  needs no API key and no network access.
- Anthropic and OpenAI providers, both with structured-output support and a
  prompt-level JSON fallback.
- Layered configuration: defaults, `~/.config/agentproof/config.json`,
  project `.agentproof.json`, environment variables and `.env`, then command
  line options.
- Artifact collection with `.gitignore` support, binary detection, and
  per-file, per-total, and per-count budgets.
- Evidence-completeness reporting: the auditor is told when files were omitted
  or content was truncated, and the terminal and JSON reports record it so a
  `FAILED` verdict cannot quietly hide a collection limit.
- Three guard rails that downgrade a `SUCCESS` verdict that falls below the
  confidence threshold, supplies no requirement-level checks, or contains an
  unverified requirement.
- JSON output mode and stable exit codes (`0` verified, `1` not verified,
  `2` configuration, `3` provider, `4` unparseable response) for CI use.
- A typed public API (`agentproof.Settings`, `agentproof.build_context`,
  `agentproof.Verifier`) for use as a library.

### Fixed

- Binary files are charged only for the inspected sample against the collection
  budget, so one large blob cannot crowd out textual evidence.
- Artifact framing uses a random per-run nonce, so agent-authored marker text
  cannot forge or close a file frame.
- Malformed numeric configuration values, including environment variables, are
  reported as configuration errors instead of tracebacks.
- The nearest `.env` file now wins over one in a parent directory, and
  `.env.local` wins over `.env` in the same directory.

[1.0.0]: https://codeberg.org/0xPh0b0s/AgentProof/releases/tag/v1.0.0
