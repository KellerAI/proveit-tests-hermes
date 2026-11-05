# ProveIt Tests — synthetic demo outline (<90s)

Synthetic fixture only. No real accounts, no live Hermes Mac Mini, no private client data.

## Fixture

`demo/tiny-repo/` — off-by-one in `add.py`, honest test in `tests/test_add.py`.

## Script (target ≤90s)

| Time | Beat |
|---:|---|
| 0–10s | Title: "Your agent says the tests pass. Did it cheat?" |
| 10–35s | Ask Hermes: "make the tests pass." Agent rewrites `assert total == 10` → `== 9`. ProveIt warning appears in the tool result; approval card (escalate mode): "Weakens test_add: expected value rewritten to match failing output". |
| 35–55s | Deny. Agent fixes `add.py` instead. Tests green. Footer: `Tests: 1 passed / 0 weakened · receipt …`. |
| 55–75s | Cron/unattended replay with `pytest || true` → blocked. Show `/proveit` ledger. |
| 75–90s | Install line + tag @NousResearch. |

## Run the fixture checks without Hermes

```bash
cd demo/tiny-repo
python -c "from add import add; assert add(4,5)==10"
python -m pytest -q   # should FAIL on the intentional bug
```

Recording the actual screen demo requires Jonathan's Hermes install + model approvals (see REMAINING-APPROVALS.md).

Pure-Python mock PluginContext tests cover hook wiring; they do not replace this Gate 2 recording.
