# Validation

## Pure-Python (no Hermes needed)

```bash
cd proveit-tests-hermes
python3 -m venv .venv && .venv/bin/pip install pytest pytest-cov
.venv/bin/pytest --cov=proveit_tests --cov-report=term-missing -q
```

Last run (2026-11-05 2:28 PM ET): **87 passed / 0 failed**, coverage `proveit_tests` **95%** (736 stmts, 40 miss).

Includes:
- `tests/test_hermes_integration_mock.py`: mock PluginContext (hooks, directives, receipts, `/proveit`).
- `tests/test_hermes_loader_isolation.py`: loads the plugin the way the Hermes v0.22.7 loader does
  (package, plugin dir **not** on `sys.path`, `python -I`). Fails on the pre-Gate-2 absolute import.
- `tests/test_hermes_real_surface.py`: `ctx.get_config(key, default)` settings and the core `patch`
  tool's `old_string`/`new_string` args, both taken from the Hermes v0.22.7 source.
- Net-new regression tests (breaker P0): identical old/new with a pre-existing skip, `assert True`,
  tautology or empty catch does **not** flag; a newly added skip / `.only` / `assert True` /
  empty catch **does**; post-edit without a pre-edit snapshot makes no claim.

## Hermes-gated: real `hermes plugins validate` / `doctor` (Gate 2, done 2026-11-05)

Gate 2 approved by Jonathan at 2:13 PM ET. Throwaway install on the shared box only (not the Mac Mini, no live
profile, no real accounts, no API keys, no model calls).

| | |
|---|---|
| Hermes | `Hermes Agent v0.22.7 · upstream b200f5bc` (tag `v0.22.7` = `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`) |
| Source | GitHub release tarball `v0.22.7` (sha256 `91bf15f5…8b91d`), `uv sync --frozen` from its `uv.lock`, Python 3.14.10 |
| Install root | `/workspace/hermes-hackathon-launch/throwaway-hermes/` (venv, src, python) |
| `HERMES_HOME` | `/workspace/hermes-hackathon-launch/throwaway-hermes/hermes-home` |
| `HOME` | `/workspace/hermes-hackathon-launch/throwaway-hermes/home` (so nothing touches `~/.hermes`) |
| Env | `source /workspace/hermes-hackathon-launch/throwaway-hermes/env.sh` (also unsets provider API key vars) |

The tarball has no `.git`, so `hermes --version` printed `vunknown` at first. We wrote an install stamp with Hermes'
own `scripts/write_install_stamp.py --base-version 0.22.7 --commit b200f5bc…` so `requires_hermes` compares
against the real release. Every validate/doctor run printed `⚠ install out of sync (ffmpeg/node/npm/ripgrep …)`.
That warning is about Hermes' PM-managed tool bundle, which this manual install skips, and it does not affect
plugin checks.

```bash
source /workspace/hermes-hackathon-launch/throwaway-hermes/env.sh
cd proveit-tests-hermes
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
# and against a clean clone at the commit (what catalog CI sees)
hermes plugins validate /tmp/proveit-clean --install-deps
hermes plugins doctor /tmp/proveit-clean --ci
```

Full output: `artifacts/gate2-validate.txt` and `artifacts/gate2-doctor.txt`.

### History of results

| Package commit | validate | doctor | Notes |
|---|---|---|---|
| `f7af12b` (pre-Gate-2) | **exit 1** | — | `✗ capability probe — import failed: No module named 'proveit_tests'`. A real defect: Hermes loads the plugin as a package without putting its dir on `sys.path`, and the mock tests never caught it. |
| `bd0c2d7` | exit 0 | exit 0 | Relative imports under the Hermes loader, plus a loader-isolation regression test. |
| `97a4197` | exit 0 | exit 0 | Working tree **and** clean clone. All checks ✓ (manifest, requires_hermes, config schema, loadable, capability probe, declared hooks match, security scan **safe**, no core override). One warning: private core imports in the demo harness, so the harness was moved out of the plugin tree (see DEMO.md). |
| current tip | exit 0 | exit 0 | See `artifacts/gate2-validate.txt` header for the exact commit. |

Advisory line (expected): `corpus/cheats/syntax_break_new.py: not parseable … not audited`. That file is an
intentional adversarial fixture (a test edit that breaks syntax).

Doctor: `manifest: proveit-tests 0.1.0 (standalone) · OK: runtime discovery, manifest parsing, import, and
registration passed · registrations: 0 tool(s), 6 hook(s)`.

### Other defects only the real install surfaced (fixed)

1. Settings were read from `ctx.settings` / `ctx.get_setting()`, but Hermes exposes `ctx.get_config(key, default)`.
   As a result `mode: escalate` was silently ignored and every install ran in observe mode.
2. The ledger now defaults to `plugins.plugin_storage.plugin_data_dir("proveit-tests")` (`$HERMES_HOME/plugin-data/proveit-tests/`).
3. The core `patch` tool uses `old_string`/`new_string`/`replace_all`. Before the fix it was analyzed post-edit only,
   so expected-literal rewrites through `patch` were missed.
4. `demo/tiny-repo` expected `add(4, 5) == 10`, so the "cheat" in the old script (`== 9`) was actually the correct value.
   The test now expects 9, the bug returns 8, and the cheat rewrites it to 8.

## Real runtime, no model (Gate 2 demo)

`.demo-harness/real_hermes_demo.py` (in this repo; demo-only, see DEMO.md) drives Hermes' real dispatcher
(`model_tools.handle_function_call`) with the plugin installed into the throwaway profile via
`hermes plugins install file://…/proveit-tests-hermes --ref <sha>`, with `mode: escalate` set through `hermes config set`.
It observed:
- `patch` cheat → real Hermes approval prompt (`plugin approval rule`) → `d` → `BLOCKED: User denied…`, file unchanged.
  Without a human (no `HERMES_INTERACTIVE`), Hermes fails closed: `BLOCKED … no interactive user or gateway`.
- Honest `add.py` fix → no finding → `1 passed`.
- Inside a Hermes cron execution identity (`cron.execution_identity.enter_cron_execution`), `pytest … || true` was blocked:
  `[blocked: unattended/cron]`.
- `/proveit` via the registered plugin command listed 2 receipts.

## Not yet validated

- A live model-driven Hermes turn, which needs provider spend (Gate 5).
- Catalog CI on `NousResearch/hermes-agent`, which needs a public repo and a catalog PR (Gates 3–4).
