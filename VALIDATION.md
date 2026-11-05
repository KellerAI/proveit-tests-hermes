# Validation checklist

## Pure-Python (runs now — no Hermes)

```bash
cd proveit-tests-hermes
python3 -m venv .venv
.venv/bin/pip install pytest pytest-cov
.venv/bin/pytest --cov=proveit_tests --cov-report=term-missing -q
```

Expected: all tests pass (including `tests/test_hermes_integration_mock.py` and
`tests/test_corpus_adversarial.py`). Coverage on `proveit_tests` reported in STATUS.md
(target ≥90%).

Mock PluginContext tests exercise `register(ctx)`, hook directives (`approve` /
`block` + `rule_key`), receipts, `/proveit`, observe warnings, and unattended
blocking. They do **not** replace real Hermes validation.

## Hermes-gated (do **not** run until Jonathan approves Gate 2 install)

```bash
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
```

These require Hermes `>=0.22.7` on an isolated throwaway profile — not the Mac Mini
live instance, not real user accounts. See REMAINING-APPROVALS.md.

## Adversarial / false-positive spot checks

- Replay every file under `corpus/cheats/` → must produce at least one open (non-waived) finding.
- Replay legit pairs under `corpus/legit/` (extract helper, rename test, reformat, type hints, waiver) → must not produce open critical weakenings of the kinds under test.
- Confirm `# proveit: intended <reason>` waives and appears in the receipt.
