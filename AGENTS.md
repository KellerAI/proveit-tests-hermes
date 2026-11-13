# AGENTS.md

## Purpose

`proveit-tests` is a Hermes Agent plugin that flags recognizable ways an agent weakens tests to reach green: removed asserts, skips, deleted tests, rewritten expected values, tautologies, swallowed failures, runner escape hatches, CI soft-fail flags, pytest config narrowing and `conftest.py` collection hooks. It is deterministic (Python AST plus regex) and makes no LLM or network calls. Full behavior, modes and limits are in `README.md`.

## Repo layout

- `plugin.yaml` - Hermes plugin manifest
- `__init__.py`, `proveit_tests/` - plugin code
- `tests/` - pytest suite, including mock Hermes integration tests
- `corpus/cheats/` (must flag) and `corpus/legit/` (false-positive control)
- `CHANGELOG.md`, `STATUS.md`, `VALIDATION.md`, `REMAINING-APPROVALS.md`, `DEMO.md`

## Setup and tests

No Hermes install is needed for development:

```bash
python3 -m venv .venv && .venv/bin/pip install pytest pytest-cov
.venv/bin/pytest --cov=proveit_tests --cov-report=term-missing -q
```

Requires Hermes `>=0.22.7` at runtime.

## Rules for agents

- This repo exists to catch test weakening. Never skip, delete or loosen a test, and never narrow pytest config to make a run pass. Fix the code, or add a logged `# proveit: intended <reason>` waiver and say why.
- Keep the plugin local-only: no network calls, telemetry or model spend.
- The receipt ledger stays inside the Hermes plugin data dir. Don't add writes to `/tmp` or other shared paths.
- New detectors need a `corpus/cheats/` case that must flag and, where relevant, a `corpus/legit/` case that must not.
- Keep JS/TS claims honest. Those detectors are heuristic, and the README says so.
- Public release, catalog listing and demo posts are held. See `REMAINING-APPROVALS.md` and don't act on them without maintainer approval.
- Update `CHANGELOG.md` for user-visible changes.
