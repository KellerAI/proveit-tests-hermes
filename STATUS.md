# ProveIt Tests — STATUS (2026-11-05, America/New_York)

## Launch

- Path: `/workspace/hermes-hackathon-launch/proveit-tests-hermes/`
- Remote: https://github.com/KellerAI/proveit-tests-hermes (private, KellerAI entrant)
- Contributions as son-of-anton-ai (write-only); no public publish yet.

## Tree layout

```
proveit-tests-hermes/
├── plugin.yaml              # native manifest, requires_hermes >=0.22.7
├── __init__.py              # register(ctx) + rule_key escalate directives
├── pyproject.toml
├── LICENSE                  # MIT
├── README.md
├── DEMO.md
├── VALIDATION.md
├── REMAINING-APPROVALS.md
├── STATUS.md
├── proveit_tests/
│   ├── detectors/           # python_ast, commands, js_ts, paths, waivers
│   ├── receipts/            # SHA-256 ledger
│   ├── hooks/               # runtime + CronProbe
│   ├── findings.py
│   └── modes.py
├── tests/                   # pure-Python pytest (no Hermes) + mock PluginContext
├── corpus/{cheats,legit}/   # adversarial + legit-refactor FP controls
├── demo/tiny-repo/          # <90s synthetic fixture
└── drafts/                  # x-post, form-answers, catalog-entry.yaml (held)
```

## Milestones

| Milestone | State |
|---|---|
| `plugin.yaml` + `register(ctx)` | done |
| Python AST detectors + rename/extract FP heuristics | done |
| Terminal / CI command detectors | done |
| JS/TS heuristics + README limits | done |
| Modes observe / escalate / unattended + `rule_key` | done |
| SHA-256 receipt ledger | done |
| Expanded adversarial corpus + legit FP controls | done |
| Pure-Python pytest | **87 passed / 0 failed** |
| Coverage (`proveit_tests`) | **95%** (736 stmts, 40 miss) |
| Mock Hermes PluginContext integration tests | done; plus real-loader + real-surface tests from v0.22.7 source |
| Net-new weakening semantics (breaker P0) | done: pre-existing skips/tautologies not blamed on an edit; regression tests |
| Honest footer (breaker P1) | done: `K open weakening(s) · receipt … · last test run seen: <real pytest summary>` |
| README + rule-13 disclosures | done (contest copy scrubbed; no client material) |
| DEMO.md + tiny-repo fixture | done |
| drafts (X / form / catalog-entry) | done (placeholders; held) |
| `hermes plugins validate/doctor` | **done (Gate 2)**: Hermes v0.22.7 throwaway; validate exit 0, doctor exit 0 (`artifacts/gate2-*.txt`) |
| Recorded synthetic demo | **done, no-spend**: real Hermes runtime, scripted agent, 55 s (`demo/recordings/`) |
| Live model-driven demo beat | **gated**: Gate 5 (provider spend) |
| Public repo / catalog PR / X / form | **held** |

## Hook feasibility (aligned with public Hermes docs)

- **Pre-edit:** `pre_tool_call` on `write_file`/`patch`/`str_replace` when args carry proposed content; diff vs disk. Directives: `block` / `approve` with `rule_key=proveit-tests:test-weakening`.
- **Commands:** escape-hatch detectors on terminal tool args.
- **Post-edit fallback:** `post_tool_call` diffs disk against a `pre_tool_call` snapshot; no snapshot → no claim. Findings are net-new vs the prior file.
- **Observe:** `transform_tool_result` appends warnings the model sees.
- **Nudge:** `pre_verify` one-shot continue when unexplained weakenings remain.
- **Unattended:** `ContextCronProbe` → `ctx.current_cron_execution()`; block in escalate / block_unattended.
- **Not unbypassable.** Documented in README. Callbacks accept `**kwargs`.

## Tests (this run, 2026-11-05 2:28 PM ET)

```
87 passed
Coverage TOTAL: 736 stmts, 40 miss, 95%
```

## Gate 2 (done)

- Hermes `v0.22.7 · upstream b200f5bc`, Python 3.14.10, `HERMES_HOME=/workspace/hermes-hackathon-launch/throwaway-hermes/hermes-home`
- `hermes plugins validate . --install-deps` → exit 0; `hermes plugins doctor . --ci` → exit 0 (also on a clean clone)
- The first real validate (at `f7af12b`) **failed** (`No module named 'proveit_tests'`). It was fixed, along with three other real-install
  defects (see VALIDATION.md). The mock tests had not caught any of them.
- Demo: `demo/recordings/proveit-real-hermes-demo.{mp4,gif,cast}`. Harness: `/workspace/hermes-hackathon-launch/demo-harness/`.

## Repo

- https://github.com/KellerAI/proveit-tests-hermes (private)
- Lineage: `2bf63bd` → `c298377` → `f7af12b` (deepen) → `bd0c2d7` (loader fix) → `7b6b8db` (real surfaces) → `aeb548b` (net-new P0 + footer P1) → `97a4197` (demo) → docs tip on `main`

## Single next Jonathan gate

**Gate 5: demo model / provider spend** for one live Hermes agent turn. Keep private. No catalog PR yet. Full list: `REMAINING-APPROVALS.md`.
