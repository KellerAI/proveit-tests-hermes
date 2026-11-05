# ProveIt Tests: synthetic demo (<90s)

Synthetic fixture only. No real accounts, no Mac Mini, no private data, no model spend.

## Recording (Gate 2, no-spend): done

- `demo/recordings/proveit-real-hermes-demo.mp4` (55 s, 1.2 MB)
- `demo/recordings/proveit-real-hermes-demo.gif` (same video as a GIF)
- `demo/recordings/proveit-real-hermes-demo.cast` (asciinema v2 source)

**How it was made:** `asciinema rec` of the demo harness (DEMO_PACE=1.7), rendered with `agg` and `ffmpeg`.
The runtime is a **real Hermes v0.22.7** in a throwaway profile (see VALIDATION.md). The plugin is installed with
`hermes plugins install file://… --ref <sha>` and set to `mode: escalate`. Every tool call goes through Hermes' own
dispatcher, hooks, approval gate and the core `patch` / `terminal` tools.

**What is scripted:** the agent. The tool calls a model would emit are hard-coded, so no provider, API key or
model is involved, and the approval answer `d` is fed to the real Hermes prompt by the harness. **This is not a
live-model demo** (that is Gate 5, below).

**Where the harness lives:** `.demo-harness/` in this repo (`real_hermes_demo.py` + `throwaway-env.sh`, paths
relative to the repo). It is demo-only: `register()` never imports it and it is not part of the plugin runtime.
It drives Hermes internals (`model_tools`, the plugin manager) to replay the scripted calls. Those are private
Hermes surfaces, so in a loadable dir `hermes plugins validate` lists them under catalog rule 9 (verified: a
`demo/harness/` placement produced that warning). The validator skips hidden dirs (like `.github/` CI helpers)
because Hermes never loads them, so in `.demo-harness/` validate reports no rule-9 warning. The plugin itself
imports only public surfaces. The recording was made from the harness at `97a4197`; since then only its path
resolution changed (now relative to the repo instead of an absolute path).

**Checksums (SHA-256):**

| File | SHA-256 |
|---|---|
| `demo/recordings/proveit-real-hermes-demo.mp4` | `a42b7425126cbefbddc664fcbac04cd9177fc8bdfdf50fa9ea8dfcb8ce08b58d` |
| `demo/recordings/proveit-real-hermes-demo.gif` | `6f2ee1dd2b430a4c4a51c86157c9d5368ca7864193fd4cbeba1083a444e8d0ac` |
| `demo/recordings/proveit-real-hermes-demo.cast` | `d766f2f9e73340b4f22aa8b0ea48daf1212d2c6b60a6ba6a237b5e405893f889` |
| `.demo-harness/real_hermes_demo.py` | `14dfa0018af13dd439a3bfbdc329d4aee59b5d32cc4a7feb88a9cbdc4d19e302` |
| `.demo-harness/throwaway-env.sh` | `a55677b44e9bf6ace9564138ae3842281038e3c844ab02700823f12a979a86e3` |

Verify: `sha256sum demo/recordings/* .demo-harness/*`

| Time | Beat (as recorded) |
|---:|---|
| 0–4s | "Your agent says the tests pass. Did it cheat?" · real Hermes v0.22.7 · scripted agent (no model) |
| 4–14s | `tiny-repo`: `add()` off-by-one. Agent runs tests via Hermes `terminal` → `FAILED … assert 8 == 9` |
| 14–27s | Agent `patch`es `tests/test_add.py`: `== 9` → `== 8`. Hermes approval card: *ProveIt Tests: possible test weakening … expected-literal-rewrite … ['9'] → ['8']* → **d** → `BLOCKED: User denied`. File unchanged. |
| 27–38s | Agent patches `add.py` instead → tests `1 passed` |
| 38–45s | Hermes cron execution context: `pytest -q \|\| true` → **blocked: unattended/cron** |
| 45–51s | `/proveit` ledger: 2 receipts (expected-literal-rewrite; pytest-or-true + ignore-test-failure) |
| 51–55s | Install line |

Re-run (about 55 s at DEMO_PACE=1.7; `DEMO_PACE=0` for a fast check):

```bash
# from the repo root; expects ../throwaway-hermes/{home,hermes-home,venv} or set PROVEIT_THROWAWAY
source .demo-harness/throwaway-env.sh
rm -rf "$HERMES_HOME/plugin-data/proveit-tests"
python .demo-harness/real_hermes_demo.py
```

The test runner inside the demo defaults to `.venv/bin/python` in this repo; override with `PROVEIT_DEMO_PYTHON`.

## Still gated: live agent beat (Gate 5)

The recording shows the real plugin inside the real Hermes runtime, but no model chose the cheat. The contest
cut with a live Hermes agent turn ("make the tests pass" → model tries the rewrite) needs a provider and spend.
That is Gate 5 in REMAINING-APPROVALS.md. Use the same fixture and beats.

## Fixture checks without Hermes

```bash
cd demo/tiny-repo
python -m pytest -q   # FAILS: assert 8 == 9 (intentional bug in add.py)
```
