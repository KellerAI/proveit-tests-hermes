# ProveIt Tests for Hermes

A green test run your agent did not fake.

```text
$ git add tests/test_total.py
$ git commit -m "Fix total"
ProveIt Tests BLOCK for commit
- assert-true @ tests/test_total.py:5: Tautological assert True
$ git restore --source=HEAD --staged --worktree tests/test_total.py
$ git add src/total.py
$ python -m pytest -q
1 passed
$ git commit -m "Fix total calculation"
```

## Install

```bash
hermes plugins install KellerAI/proveit-tests-hermes --ref <40-char-sha>
hermes plugins enable proveit-tests
```

Requires Hermes `>=0.22.7`. Set the mode under
`plugins.entries.proveit-tests.settings.mode`.

## Modes

| Mode | Behavior |
|---|---|
| `block` (default) | Blocks block-tier findings at ship points and sends review-tier findings to Hermes approval. Unattended ship points block on either tier. Edits warn the agent and request approval for block-tier findings in attended sessions. The hard gate is at the ship point. |
| `escalate` | Sends findings to Hermes approval. Blocks on unattended or cron runs. |
| `warn` (alias `observe`) | Appends warnings and allows the tool call to proceed. |

`block_unattended` remains supported and escalates when attended. Approval
requests use the rule key `proveit-tests:test-weakening`.

## Ship-point gate

| Command | Comparison |
|---|---|
| `git commit`, including `--amend` | Staged index against `HEAD`. `-a` and `-am` use tracked working-tree edits too. |
| `git push` | Upstream against `HEAD`, or the merge base with the locally recorded remote default branch against `HEAD`. |
| `gh pr create` | Merge base of `--base` or the locally recorded remote default branch against `HEAD`. |
| `gh pr merge` | Requires Hermes human approval in enforcing modes. Unattended merges block. |

The gate uses terminal `workdir` or the session directory, honoring `cd` prefixes
and `git -C`. If inspection fails, block mode stops the ship command. Pass
`workdir` when the current repo is ambiguous. Stage edits in a separate tool
call so the gate can inspect the final index.

A waiver added in the inspected diff requires human review. An unchanged inline
waiver still applies. Each ship check records a `BLOCK`, `REVIEW`, or `CLEAN`
receipt with findings and available base and head commit SHAs. For a commit,
the head SHA is the current `HEAD` before the new commit exists.

At turn end, `pre_verify` can nudge once if unexplained weakenings remain. `/proveit-tests` prints the session receipt ledger. Warnings appended to tool results end with a footer like
`[ProveIt] 1 open weakening(s) · receipt 3f9c1a2b4d5e · last test run seen: 1 failed`. The
"last test run seen" part appears only when a pytest summary was actually seen in a terminal tool
result; the plugin never invents a pass count.

The open count is session-wide: it covers every watched file and command with an unresolved
finding, not just the latest edit. Later edits to the same file are re-checked against the
content before its first unresolved weakening, so restoring the original bytes (or otherwise
fixing it) clears the current warning, while the earlier receipt stays in the ledger as history.
Every non-empty edit batch is recorded, including batches with inline waivers.

Inline waiver (logged, not silent):

```python
@pytest.mark.skip(reason="flaky upstream")
def test_flaky_network():
    # proveit: intended waiting on upstream issue #42
    assert fetch() == 1
```

## CI mode

```bash
python -m proveit_tests.ci --base BASE_REF [--head HEAD] [--repo .] [--format text|json|github] [--mode block|warn]
```

Exit `0` means clean or review only, `1` means a block-tier finding in block
mode, and `2` means the range could not be inspected. Warn mode reports findings
without enforcing them. GitHub review annotations are warnings. JSON includes a
`PASS`, `WARN`, or `BLOCK` verdict and stable finding IDs.

This repository's PR workflow runs the base branch detector when available. On
the first upgrade from a base without the CI module, it prints a notice and
uses the PR version. Other repositories can pin a trusted detector commit with
[the example workflow](examples/proveit-check.yml).

## Finding tiers

| Tier | Detector rules |
|---|---|
| Review | `expected-value-changed` for in-place assertion literal changes and single-exception substitutions, heuristic `js-expected-literal-rewrite`, and ship findings with newly added waivers. PR merge commands also require review. |
| Block | All other detector rules, including deleted tests and watched files, assertion removal or weakening, renamed tests with changed expectations, assertionless or syntactically broken Python tests, skip/xfail/`.only`, tautologies, swallowed failures, runner escape hatches, CI soft-fail, pytest configuration and collection-hook narrowing, and failed ship inspection. |

A value correction and a rewrite that masks a bug can produce the same diff. Reviewers can compare
the expectation with the spec. Old receipts may show `expected-literal-rewrite`, the historical
alias for `expected-value-changed`. Receipts retain their original contents and legacy severity.

Edits to test files, pytest config files (`pyproject.toml`, `pytest.ini`, `.pytest.ini`, `setup.cfg`,
`tox.ini`), `conftest.py`, CI configs, and test-runner commands. Findings are **net-new**: each edit is
compared with the file as it was before that edit, and a skip, `assert True`, tautology or
empty catch that was already there is not attributed to the edit. A brand-new test file
counts as all-new. When the prior content is unknown, no claim is made.

| Pattern | Example |
|---|---|
| Removed / loosened asserts | assert count drops in a test |
| Skip / xfail / `.only` | `@pytest.mark.skip`, `it.skip`, `test.only` |
| Deleted test function | `test_b` disappears from the file |
| Expected value changed | `assert total == 10` → `== 9` |
| Tautology | `assert True`, `assert x == x`, `expect(true).toBe(true)` |
| Swallowed failures | `try: … except: pass` / empty `catch` |
| Runner escape hatches | `pytest \|\| true`, `-k "not …"`, `--deselect`, `--passWithNoTests` |
| CI soft-fail | `continue-on-error: true`, `allow_failure: true` |
| pytest config narrowing | net-new `addopts` `-k`, `-m`, `--deselect`, `--ignore`/`--ignore-glob`, `--co`, `--continue-on-collection-errors`, `--suppress-no-test-exit-code` in `[tool.pytest.ini_options]` / `[tool.pytest]` / `[pytest]` / `[tool:pytest]`; `testpaths` narrowed or newly set; `python_files`/`_classes`/`_functions` losing a pattern; `norecursedirs` gaining a test dir; `xfail_strict` turned off; the same `PYTEST_ADDOPTS=…` in a command; a pytest escape-hatch command added to tox `commands` or a CI `run:` line |
| `conftest.py` hooks | `pytest_collection_modifyitems` removing items (`items[:] =`, `.remove`/`.pop`/`.clear`, `del`), `pytest_deselected`, skip/xfail markers or `pytest.skip` in collection/setup hooks, `collect_ignore`/`collect_ignore_glob`, `pytest_ignore_collect`, `config.option.keyword`/`markexpr`/`deselect` overrides, report `outcome` rewrites |

For config files the net-new key is the option itself (e.g. `-k not slow`), so a `-m "not slow"` that
was already there, a version bump, a new dependency or a coverage/ruff section does not flag; changing
the `-k` expression does. A `# proveit: intended <reason>` comment can request human review at a ship point.

## Disclosure

- **Local-only.** No network calls, no telemetry, no model spend from this plugin.
- Reads the **existing file on disk** and the **proposed content / command in tool args** to compare before/after for `write_file` / `patch` / terminal tools, for watched files only: test files, CI configs, pytest config files (`pyproject.toml`, `pytest.ini`, `.pytest.ini`, `setup.cfg`, `tox.ini`) and `conftest.py`.
- Runs read-only `git` subprocesses with a minimal environment to compare local Git contents.
- May **append warnings** into tool results (`transform_tool_result`).
- May **escalate or block** tool calls according to the selected mode.
- Writes a **SHA-256 receipt ledger** (`receipts.jsonl`, dir `0700`, file `0600`) only under the Hermes plugin data directory (`$HERMES_HOME/plugin-data/proveit-tests/`). `receipt_dir` can only pick a subdirectory inside it; it cannot point the ledger elsewhere.
- If Hermes provides no plugin data directory, the ledger **fails closed to in-memory only** (logged warning; `/proveit-tests` says "in-memory only") — nothing is written to `/tmp` or any other shared location.
- **Terminal findings may retain a short excerpt of the command text locally** (≤200 chars) in that ledger as evidence. Secret-looking substrings (URL credentials, `Authorization`/bearer values, `*_TOKEN=`/`*PASSWORD=`-style env assignments, `--token`/`--password`/`--api-key` flags, common token prefixes like `ghp_`/`sk-`/`AKIA`, long opaque strings) are redacted first. Redaction is best-effort: an unusual secret format can survive, so avoid inlining credentials in test commands.
- **Not a sandbox and not unbypassable.** An agent can still rewrite files via novel shell indirections, edit outside watched globs, disable the plugin, or invent new weakenings. Treat findings as signals, not proof of malice or of safety.

## Known limits

- Not a substitute for code review, CI, or a security audit.
- Does not certify HIPAA, SOC2, or any compliance regime.
- Flags selected, recognizable weakening patterns in edits and commands it observes; absence of findings is not proof that tests were preserved, and does not prove tests are *good*.
- JS/TS detectors are heuristic and limited to recognizable test and assertion patterns.
- pytest config / `conftest.py` coverage is limited to the options and hook shapes listed above. Not
  covered: `-p no:<plugin>` or a plugin module named in `addopts`, a conftest helper that deselects via
  an indirect call or a different variable name, a `pytest_collection_modifyitems` defined outside
  `conftest.py` (e.g. a plugin module), `PYTEST_ADDOPTS` set in CI `env:` blocks or `.env` files,
  task-runner configs other than tox (`Makefile`, `package.json`, `noxfile.py`), and a config file
  that no longer parses (no claim is made). JS runner configs (`jest.config.*`, `vitest.config.*`) are
  not watched.
- Exception widening checks recognize direct `pytest.raises` calls, explicit tuple widening,
  and broad built-in exception types. Exception hierarchies and aliases are unresolved.

- Python assertion pairing and rename detection are heuristic. Helper extraction is allowed when
  module assertion counts are preserved, which can hide removals offset by unrelated additions.
- The terminal gate inspects the local checkout and refs before the shell runs. It can require
  a separate command when an earlier command could change the inspected state. Shell indirection,
  Git aliases, custom filters, command substitutions, direct API calls and remote terminal
  environments can evade or invalidate local inspection. Changes to refs made after inspection
  can race the gate. When proposed edit contents are unavailable, the edit hook relies on a
  post-edit disk snapshot.
- CI compares the two supplied snapshots and uses its default watch paths. It cannot inspect an
  agent's uncommitted work or terminal commands.

## Config

Settings under `plugins.entries.proveit-tests.settings` (also the Desktop settings form via `config_schema`):

| Key | Default | Meaning |
|---|---|---|
| `mode` | `block` | See the modes above |
| `test_path_globs` | `test_*.py`, `*_test.py`, `tests/**`, `*.test.js/ts`, `*.spec.js/ts`, `__tests__/**` | Paths treated as tests |
| `ci_path_globs` | `.github/workflows/**`, `.gitlab-ci.yml`, … | CI configs watched for soft-fail flags and net-new pytest escape-hatch `run:` lines |

| `receipt_dir` | `""` (plugin data dir) | Optional **relative** subdirectory under the Hermes plugin data dir. Absolute, `~`, or escaping (`..`/symlink) values are rejected with a warning and the plugin data dir is used |
| `one_shot_nudge` | `true` | `pre_verify` continues once when weakenings remain |

pytest config files and `conftest.py` are always watched by filename.

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

## Credits

Thanks to Sachin for the independent fast pass against `2412a18`, which found the waived-batch
ledger gap, the stale status after an exact restoration, and the per-batch open count fixed in
this release (see `CHANGELOG.md`).

## License

MIT. ProveIt brand — standalone plugin, not affiliated with Nous Research beyond the Hermes plugin API.

## Contest

Entered in the Nous Research Hermes plugin hackathon.
