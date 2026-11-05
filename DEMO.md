# ProveIt Tests: synthetic demo (<90s)

Synthetic fixture only. No real accounts, no Mac Mini, no private data, no model spend.

## Recording (Gate 2, no-spend): done

- `demo/recordings/proveit-real-hermes-demo.mp4` (55 s, 1.2 MB)
- `demo/recordings/proveit-real-hermes-demo.gif` (same video as a GIF)
- `demo/recordings/proveit-real-hermes-demo.cast` (asciinema v2 source)

**How it was made:** `asciinema rec` of
`/workspace/hermes-hackathon-launch/demo-harness/real_hermes_demo.py` (DEMO_PACE=1.7), rendered with `agg` and
`ffmpeg`. The runtime is a **real Hermes v0.22.7** in the throwaway profile (see VALIDATION.md). The plugin is
installed with `hermes plugins install file://… --ref <sha>` and set to `mode: escalate`. Every tool call goes through
Hermes' own dispatcher, hooks, approval gate and the core `patch` / `terminal` tools.

**What is scripted:** the agent. The tool calls a model would emit are hard-coded, so no provider or API key
is involved, and the approval answer `d` is fed to the real Hermes prompt by the harness.

**Why the harness lives outside the repo:** it imports Hermes internals (`model_tools`, the plugin manager).
Inside the plugin tree, `hermes plugins validate` warns about that under catalog rule 9. The recording was made
from the in-repo copy at `97a4197`. The harness logic is unchanged since then; only its path resolution moved.

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
source /workspace/hermes-hackathon-launch/throwaway-hermes/env.sh
rm -rf "$HERMES_HOME/plugin-data/proveit-tests"
python /workspace/hermes-hackathon-launch/demo-harness/real_hermes_demo.py
```

## Still gated: live agent beat (Gate 5)

The recording shows the real plugin inside the real Hermes runtime, but no model chose the cheat. The contest
cut with a live Hermes agent turn ("make the tests pass" → model tries the rewrite) needs a provider and spend.
That is Gate 5 in REMAINING-APPROVALS.md. Use the same fixture and beats.

## Fixture checks without Hermes

```bash
cd demo/tiny-repo
python -m pytest -q   # FAILS: assert 8 == 9 (intentional bug in add.py)
```
