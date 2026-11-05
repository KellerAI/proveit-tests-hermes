# Remaining Jonathan approvals

Ordered. Ask **one gate at a time**.

## Gate 1 — DONE (2026-11-05)

Private repo created and seeded:
- URL: https://github.com/KellerAI/proveit-tests-hermes (private)
- Owner: KellerAI (entrant identity)
- Created as jonathan-kellerai; son-of-anton-ai write-only
- Tree pushed on `main` (lineage from `2bf63bd`; see STATUS.md for tip)

## Gate 2 (NEXT) — Hermes install for validate/doctor + recorded demo

Approve installing Hermes `>=0.22.7` in a **throwaway profile on the box** (not Mac Mini live Hermes, not real user accounts) so we can run:

- `hermes plugins validate . --install-deps`
- `hermes plugins doctor . --ci`
- Synthetic recorded demo (<90s) against the throwaway profile

Without this gate, pure-Python unit + mock-PluginContext tests alone are not submission-ready — real validate/doctor + recorded demo still required.

## Gate 3 — Go public + license attribution

OK to flip the repo **public** with ProveIt name / MIT attribution text.

## Gate 4 — Catalog PR author

Who opens `plugin-catalog/proveit-tests.yaml` on `NousResearch/hermes-agent` (rule 5).

## Gate 5 — Demo model / provider spend

Approve model for the <90s synthetic demo (any spend).

## Gate 6 — Jonathan posts X + submits form

Jonathan reviews drafts + video, posts himself, submits form (email + Discord still unresolved).

---

**Held until explicit yes:** public visibility, catalog PR, X, form, Hermes binary install, model spend.
