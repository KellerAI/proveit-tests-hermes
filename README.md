# ProveIt Tests for Hermes

A native [Hermes Agent](https://hermes-agent.nousresearch.com/) plugin that catches an agent **weakening tests** to reach green.

Deterministic (Python AST + regex). No LLM calls. Complements core verify-on-stop and claim-vs-evidence plugins — those check that tests *ran* or that *claims* match tool evidence; this checks whether the tests still *test* anything.

> **Language coverage:** Python-strong. JS/TS detectors are **heuristic and limited** (regex over `it`/`test`/`expect`/`skip`/`only`). Do not treat JS/TS results as complete.

## What it catches

Edits to test files and test-runner / CI commands:

| Pattern | Example |
|---|---|
| Removed / loosened asserts | assert count drops in a test |
| Skip / xfail / `.only` | `@pytest.mark.skip`, `it.skip`, `test.only` |
| Deleted test function | `test_b` disappears from the file |
| Expected literal rewritten | `assert total == 10` → `== 9` to match a bug |
| Tautology | `assert True`, `assert x == x`, `expect(true).toBe(true)` |
| Swallowed failures | `try: … except: pass` / empty `catch` |
| Runner escape hatches | `pytest \|\| true`, `-k "not …"`, `--deselect`, `--passWithNoTests` |
| CI soft-fail | `continue-on-error: true`, `allow_failure: true` |

## Modes

| Mode | Behavior |
|---|---|
| `observe` (default) | Append a warning to the tool result (model sees it). Never blocks. |
| `escalate` | `pre_tool_call` returns `{"action":"approve","rule_key":"proveit-tests:test-weakening"}` → Hermes human-approval gate. Blocks on cron/unattended. |
| `block_unattended` | Blocks when `ctx.current_cron_execution()` is set; otherwise escalates (same `rule_key`). |

At turn end, `pre_verify` can nudge once if unexplained weakenings remain. `/proveit` prints the session receipt ledger. Footer shape: `Tests: N passed / K weakened · receipt <hash>`.

Inline waiver (logged, not silent):

```python
@pytest.mark.skip(reason="flaky upstream")
def test_flaky_network():
    # proveit: intended waiting on upstream issue #42
    assert fetch() == 1
```

## Install

```bash
# once this repo is public and catalog-listed (not yet — see REMAINING-APPROVALS.md)
hermes plugins install proveit-tests
hermes plugins enable proveit-tests
```

From a local checkout (development):

```bash
hermes plugins install /path/to/proveit-tests-hermes
hermes plugins enable proveit-tests
```

Requires Hermes `>=0.22.7`.

## Config

Settings under `plugins.entries.proveit-tests.settings` (also the Desktop settings form via `config_schema`):

| Key | Default | Meaning |
|---|---|---|
| `mode` | `observe` | `observe` \| `escalate` \| `block_unattended` |
| `test_path_globs` | `test_*.py`, `*_test.py`, `tests/**`, `*.test.js/ts`, `*.spec.js/ts`, `__tests__/**` | Paths treated as tests |
| `ci_path_globs` | `.github/workflows/**`, `.gitlab-ci.yml`, … | CI configs watched for soft-fail flags |
| `receipt_dir` | plugin data dir | Override receipt ledger location |
| `one_shot_nudge` | `true` | `pre_verify` continues once when weakenings remain |

## Security disclosure (catalog rule 13)

- **Local-only.** No network calls, no telemetry, no model spend from this plugin.
- Reads the **existing file on disk** and the **proposed content / command in tool args** to compare before/after for `write_file` / `patch` / terminal tools.
- May **append warnings** into tool results (`transform_tool_result`).
- May **escalate or block** tool calls when mode is not `observe`.
- Writes a **SHA-256 receipt ledger** under the plugin data directory.
- **Not a sandbox and not unbypassable.** An agent can still rewrite files via novel shell indirections, edit outside watched globs, disable the plugin, or invent new weakenings. Treat findings as signals, not proof of malice or of safety.

## Hook feasibility (honest)

| Seam | What we can see | Enforcement |
|---|---|---|
| `pre_tool_call` on `write_file` / `patch` | Proposed content in `args` + current disk file | Pre-edit observe / escalate / block |
| `pre_tool_call` on `terminal` | Command string only | Escape-hatch command detectors; not full AST of files rewritten via shell |
| `post_tool_call` | Re-read disk after writes / likely redirections | Post-edit observe when pre-edit content was missing |
| `transform_tool_result` | Append warning the model sees | Observe mode |
| `pre_verify` | `changed_paths`, one-shot continue | Nudge to restore or waive |
| `current_cron_execution()` | Unattended/cron detection | Fail closed in escalate / block_unattended |

If a future Hermes build stops putting file contents in write/patch args, pre-edit AST diffs degrade to post-edit observe — the plugin still loads; behavior is documented here rather than promised as unbypassable.

## What this does **not** guarantee

- Not a substitute for code review, CI, or a security audit.
- Does not certify HIPAA, SOC2, or any compliance regime.
- Does not prove tests are *good* — only that common weakenings were not just introduced.
- JS/TS coverage is incomplete by design in v0.1.

## Development (no Hermes required)

```bash
python3 -m venv .venv && .venv/bin/pip install pytest pytest-cov
.venv/bin/pytest --cov=proveit_tests --cov-report=term-missing -q
```

Golden corpus under `corpus/cheats/` (must flag) and `corpus/legit/` (false-positive control:
extract-to-helper, rename test, reformat, type hints, `# proveit: intended` waivers).
Mock Hermes PluginContext integration tests live in `tests/test_hermes_integration_mock.py`
(pure Python — real `hermes plugins validate`/`doctor` still needs Gate 2).

## License

MIT. ProveIt brand — standalone plugin, not affiliated with Nous Research beyond the Hermes plugin API.

## Catalog / contest status

Private draft package. Public repo, catalog PR, X demo post, and form submission are **held** pending maintainer approval — see `REMAINING-APPROVALS.md`.
