# Validation checklist

## Pure-Python (runs now — no Hermes)

```bash
cd proveit-tests-hermes
python3 -m venv .venv
.venv/bin/pip install pytest coverage
.venv/bin/coverage run -m pytest -q
.venv/bin/coverage report --include='proveit_tests/*'
```

Expected: all tests pass. Coverage on `proveit_tests` reported in STATUS.md.

## Hermes-gated (do **not** run until Jonathan approves an install)

```bash
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
```

These require Hermes `>=0.22.7` on an isolated throwaway profile — not the Mac Mini live instance, not real user accounts. See REMAINING-APPROVALS.md.

## Adversarial / false-positive spot checks

- Replay every file under `corpus/cheats/` → must produce at least one open (non-waived) finding.
- Replay every pair under `corpus/legit/` → must not produce open critical weakenings of the kinds under test.
- Confirm `# proveit: intended <reason>` waives and appears in the receipt.
