# Remaining Jonathan approvals

Ordered. Ask **one gate at a time**.

## Gate 1: DONE (2026-11-05)

Private repo https://github.com/KellerAI/proveit-tests-hermes (KellerAI; son-of-anton-ai write-only).

## Gate 2: DONE (approved 2026-11-05 2:13 PM ET)

Throwaway Hermes v0.22.7 install on the shared box under `/workspace/hermes-hackathon-launch/throwaway-hermes/`
(isolated `HOME` + `HERMES_HOME`; Mac Mini, live profiles and accounts untouched; no model spend).
- `hermes plugins validate . --install-deps`: **exit 0** (working tree + clean clone)
- `hermes plugins doctor . --ci`: **exit 0**
- No-spend recording on the real runtime: `demo/recordings/proveit-real-hermes-demo.mp4` (55 s)
- Real-install defects found and fixed: loader import, `get_config` settings, `patch` args, fixture expectation. See VALIDATION.md.

## Gate 5 (NEXT): demo model / provider spend

Approve a model/provider (and spend cap) for one live Hermes agent turn on the synthetic `tiny-repo`, recorded
in the throwaway profile, so the contest video shows a model actually attempting the test rewrite. Without it
the no-spend recording above is the demo.

## Gate 3: go public + license attribution

OK to flip the repo **public** with ProveIt name / MIT attribution text.

## Gate 4: catalog PR author

Who opens `plugin-catalog/proveit-tests.yaml` on `NousResearch/hermes-agent` (rule 5).

## Gate 6: Jonathan posts X + submits form

Jonathan reviews drafts + video, posts himself, submits form (email + Discord still unresolved).

---

**Held until an explicit yes:** model spend, public visibility, catalog PR, X, form.
