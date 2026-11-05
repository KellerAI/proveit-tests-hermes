# ProveIt Tests for Hermes

A native [Hermes Agent](https://hermes-agent.nousresearch.com/) plugin that flags recognizable ways an agent **weakens tests** to reach green.

Deterministic (Python AST + regex). No LLM calls. Complements core verify-on-stop and claim-vs-evidence plugins — those check that tests *ran* or that *claims* match tool evidence; this checks whether the tests still *test* anything.

> **Language coverage:** Python-strong. JS/TS detectors are **heuristic and limited** (regex over `it`/`test`/`expect`/`skip`/`only`). Do not treat JS/TS results as complete.

## What it flags

Edits to test files and test-runner / CI commands. Findings are **net-new**: each edit is
compared with the file as it was before that edit, and a skip, `assert True`, tautology or
empty catch that was already there is not attributed to the edit. A brand-new test file
counts as all-new. When the prior content is unknown, no claim is made.

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

At turn end, `pre_verify` can nudge once if unexplained weakenings remain. `/proveit` prints the session receipt ledger. Warnings appended to tool results end with a footer like
`[ProveIt] 1 open weakening(s) · receipt 3f9c1a2b4d5e · last test run seen: 1 failed`. The
"last test run seen" part appears only when a pytest summary was actually seen in a terminal tool
result; the plugin never invents a pass count.

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

From a local git checkout (development; `install` takes a Git URL, so pin a commit):

```bash
hermes plugins install file:///path/to/proveit-tests-hermes --ref <40-char-commit-sha> --enable
hermes config set plugins.entries.proveit-tests.settings.mode escalate   # optional
```

Requires Hermes `>=0.22.7`.

## Config

Settings under `plugins.entries.proveit-tests.settings` (also the Desktop settings form via `config_schema`):

| Key | Default | Meaning |
|---|---|---|
| `mode` | `observe` | `observe` \| `escalate` \| `block_unattended` |
| `test_path_globs` | `test_*.py`, `*_test.py`, `tests/**`, `*.test.js/ts`, `*.spec.js/ts`, `__tests__/**` | Paths treated as tests |
| `ci_path_globs` | `.github/workflows/**`, `.gitlab-ci.yml`, … | CI configs watched for soft-fail flags |
| `receipt_dir` | `""` (plugin data dir) | Optional **relative** subdirectory under the Hermes plugin data dir. Absolute, `~`, or escaping (`..`/symlink) values are rejected with a warning and the plugin data dir is used |
| `one_shot_nudge` | `true` | `pre_verify` continues once when weakenings remain |

## Security disclosure (catalog rule 13)

- **Local-only.** No network calls, no telemetry, no model spend from this plugin.
- Reads the **existing file on disk** and the **proposed content / command in tool args** to compare before/after for `write_file` / `patch` / terminal tools.
- May **append warnings** into tool results (`transform_tool_result`).
- May **escalate or block** tool calls when mode is not `observe`.
- Writes a **SHA-256 receipt ledger** (`receipts.jsonl`, dir `0700`, file `0600`) only under the Hermes plugin data directory (`$HERMES_HOME/plugin-data/proveit-tests/`). `receipt_dir` can only pick a subdirectory inside it; it cannot point the ledger elsewhere.
- If Hermes provides no plugin data directory, the ledger **fails closed to in-memory only** (logged warning; `/proveit` says "in-memory only") — nothing is written to `/tmp` or any other shared location.
- **Terminal findings may retain a short excerpt of the command text locally** (≤200 chars) in that ledger as evidence. Secret-looking substrings (URL credentials, `Authorization`/bearer values, `*_TOKEN=`/`*PASSWORD=`-style env assignments, `--token`/`--password`/`--api-key` flags, common token prefixes like `ghp_`/`sk-`/`AKIA`, long opaque strings) are redacted first. Redaction is best-effort: an unusual secret format can survive, so avoid inlining credentials in test commands.
- **Not a sandbox and not unbypassable.** An agent can still rewrite files via novel shell indirections, edit outside watched globs, disable the plugin, or invent new weakenings. Treat findings as signals, not proof of malice or of safety.

## Hook feasibility (honest)

| Seam | What we can see | Enforcement |
|---|---|---|
| `pre_tool_call` on `write_file` / `patch` | Proposed content in `args` + current disk file | Pre-edit observe / escalate / block |
| `pre_tool_call` on `terminal` | Command string only | Escape-hatch command detectors; not full AST of files rewritten via shell |
| `post_tool_call` | Disk after the tool vs a snapshot taken in `pre_tool_call` (write/patch without content in args, or a terminal command naming a watched test/CI path) | Post-edit observe; no snapshot → no claim |
| `transform_tool_result` | Append warning the model sees | Observe mode |
| `pre_verify` | `changed_paths`, one-shot continue | Nudge to restore or waive |
| `current_cron_execution()` | Unattended/cron detection | Fail closed in escalate / block_unattended |

If a future Hermes build stops putting file contents in write/patch args, pre-edit AST diffs degrade to post-edit observe — the plugin still loads; behavior is documented here rather than promised as unbypassable.

## What this does **not** guarantee

- Not a substitute for code review, CI, or a security audit.
- Does not certify HIPAA, SOC2, or any compliance regime.
- Flags selected, recognizable weakening patterns in edits and commands it observes; absence of findings is not proof that tests were preserved, and does not prove tests are *good*.
- JS/TS coverage is incomplete by design in v0.1.

## Development (no Hermes required)

```bash
python3 -m venv .venv && .venv/bin/pip install pytest pytest-cov
.venv/bin/pytest --cov=proveit_tests --cov-report=term-missing -q
```

Golden corpus under `corpus/cheats/` (must flag) and `corpus/legit/` (false-positive control:
extract-to-helper, rename test, reformat, type hints, `# proveit: intended` waivers).
Mock Hermes PluginContext integration tests live in `tests/test_hermes_integration_mock.py`;
`tests/test_hermes_loader_isolation.py` and `tests/test_hermes_real_surface.py` pin the loader and
`ctx.get_config` / `patch` shapes of Hermes v0.22.7. Real `hermes plugins validate` / `doctor`
results are in `VALIDATION.md`.

## License

MIT. ProveIt brand — standalone plugin, not affiliated with Nous Research beyond the Hermes plugin API.

## Catalog / contest status

Private draft package. Public repo, catalog PR, X demo post, and form submission are **held** pending maintainer approval — see `REMAINING-APPROVALS.md`.
