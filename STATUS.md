# ProveIt Tests — STATUS (2026-11-05, America/New_York)

## Launch

- Started: Black Team cloud build on shared box (greenfield; no remote clone).
- Path: `/workspace/hermes-hackathon-launch/proveit-tests-hermes/`
- Origin `new_repo` blocked → local tree + git history only; push waits on Gate 1.

## Tree layout

```
proveit-tests-hermes/
├── plugin.yaml              # native manifest, requires_hermes >=0.22.7
├── __init__.py              # register(ctx)
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
├── tests/                   # pure-Python pytest (no Hermes)
├── corpus/{cheats,legit}/   # golden corpus
├── demo/tiny-repo/          # <90s synthetic fixture
└── drafts/                  # x-post, form-answers, catalog-entry.yaml
```

## Milestones

| Milestone | State |
|---|---|
| `plugin.yaml` + `register(ctx)` | done |
| Python AST detectors | done |
| Terminal / CI command detectors | done |
| JS/TS heuristics + README limits | done |
| Modes observe / escalate / unattended | done (`current_cron_execution` behind `CronProbe`) |
| SHA-256 receipt ledger | done |
| Golden corpus cheats vs legit + waiver | done |
| Pure-Python pytest | **40 passed / 0 failed** |
| Coverage (`proveit_tests`) | **82%** (660 stmts, 119 miss) |
| README + rule-13 disclosures | done (public copy scrubbed for contest copy rules) |
| DEMO.md + tiny-repo fixture | done |
| drafts (X / form / catalog-entry) | done (placeholders) |
| `hermes plugins validate/doctor` | **gated** — needs Gate 2 |
| Public repo / catalog PR / X / form | **held** |

## Hook feasibility

- **Pre-edit:** `pre_tool_call` on `write_file`/`patch` when args carry proposed content; diff vs disk.
- **Commands:** escape-hatch detectors on terminal tool args (`pytest || true`, `-k not`, `--deselect`, `--passWithNoTests`, …).
- **Post-edit fallback:** `post_tool_call` re-reads disk when pre-edit content was missing (e.g. shell redirects).
- **Observe:** `transform_tool_result` appends warnings the model sees.
- **Nudge:** `pre_verify` one-shot continue when unexplained weakenings remain.
- **Unattended:** `ContextCronProbe` → `ctx.current_cron_execution()`; block in escalate / block_unattended.
- **Not unbypassable.** Documented in README. No claim of pre-edit enforcement for arbitrary shell rewrites.

## Tests (this run)

```
40 passed in ~0.5s
Coverage TOTAL: 660 stmts, 119 miss, 82%
```

## Single next Jonathan gate

**Create an empty private GitHub repo** (name proposal `proveit-tests-hermes`; owner/identity still unresolved — personal vs KellerAI org) so this push-ready tree can be pushed via cloud. Keep it private. Do not open a catalog PR yet. Full list: `REMAINING-APPROVALS.md`.
