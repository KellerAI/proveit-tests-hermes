# Remaining Jonathan approvals

Ordered. Ask **one gate at a time**. Everything above a gate that is already unblocked should keep moving.

## Gate 1 (NEXT — blocking cloud push) — create empty private GitHub repo

Origin `new_repo` is blocked for this account. Jonathan (or an approved identity) creates an **empty private** GitHub repository, then the Black Team pushes the push-ready tree from this box.

Proposed defaults (edit before creating):

| Field | Proposal |
|---|---|
| Owner | **UNRESOLVED** — `jonathan-kellerai` (personal) vs KellerAI org (Decision 2 in yeet sheet) |
| Name | `proveit-tests-hermes` |
| Visibility | **private** for first push; public comes later as its own gate |
| License | MIT (already in tree) — confirm |
| Description | Native Hermes plugin that catches agents weakening tests |

Once the empty repo URL exists, say: *push this tree to \<url\>*. No public catalog PR yet.

## Gate 2 — Hermes install for validate/doctor

Approve installing Hermes `>=0.22.7` in a **throwaway profile on this box** (not Mac Mini live Hermes, not real user accounts) so we can run:

- `hermes plugins validate . --install-deps`
- `hermes plugins doctor . --ci`

## Gate 3 — Entrant identity + go public

Confirm repo owner / prize identity, license attribution text, and OK to flip the repo **public** with the ProveIt name.

## Gate 4 — Catalog PR author

Who opens the PR adding `plugin-catalog/proveit-tests.yaml` to `NousResearch/hermes-agent` (rule 5 ties entrant to owner/major contributor).

## Gate 5 — Demo model / provider spend

Approve which model records the <90s synthetic demo (and any spend).

## Gate 6 — Jonathan posts X + submits form

Jonathan reviews `drafts/x-post.md` + video, posts himself, then submits `drafts/form-answers.md` (email + Discord still unresolved).

---

**Held until explicit yes:** public repo creation/publication, public catalog PR, X posting, form submission, Hermes binary install, model spend, any download that needs approval.
