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
| Pure-Python pytest | **73 passed / 0 failed** |
| Coverage (`proveit_tests`) | **94%** (684 stmts, 40 miss) |
| Mock Hermes PluginContext integration tests | done (document Gate 2 still required) |
| README + rule-13 disclosures | done (contest copy scrubbed; no client material) |
| DEMO.md + tiny-repo fixture | done |
| drafts (X / form / catalog-entry) | done (placeholders; held) |
| `hermes plugins validate/doctor` | **gated** — needs Gate 2 |
| Recorded synthetic demo | **gated** — needs Gate 2 |
| Public repo / catalog PR / X / form | **held** |

## Hook feasibility (aligned with public Hermes docs)

- **Pre-edit:** `pre_tool_call` on `write_file`/`patch`/`str_replace` when args carry proposed content; diff vs disk. Directives: `block` / `approve` with `rule_key=proveit-tests:test-weakening`.
- **Commands:** escape-hatch detectors on terminal tool args.
- **Post-edit fallback:** `post_tool_call` re-reads disk when pre-edit content was missing.
- **Observe:** `transform_tool_result` appends warnings the model sees.
- **Nudge:** `pre_verify` one-shot continue when unexplained weakenings remain.
- **Unattended:** `ContextCronProbe` → `ctx.current_cron_execution()`; block in escalate / block_unattended.
- **Not unbypassable.** Documented in README. Callbacks accept `**kwargs`.

## Tests (this run)

```
73 passed
Coverage TOTAL: 684 stmts, 40 miss, 94%
```

Real `hermes plugins validate` / `doctor` and a recorded demo still need Gate 2 (Hermes install on a throwaway box profile). Mock integration tests are not a substitute.

## Repo

- https://github.com/KellerAI/proveit-tests-hermes (private)
- Lineage: `2bf63bd` → `c298377` (docs) → deepening commit on `main`

## Single next Jonathan gate

**Gate 2 — Hermes throwaway-box install** (>=0.22.7) for `validate`/`doctor` and recorded synthetic demo. Keep private. Do not open a catalog PR yet. Full list: `REMAINING-APPROVALS.md`.
