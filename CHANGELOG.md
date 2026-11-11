# Changelog

## Unreleased

Fixes from Sachin's independent fast pass against `2412a18` (169 passing, 4/4 sampled
patterns warned, three confirmed bugs). Thanks, Sachin.

### Fixed

- **Fully waived batches now reach the ledger.** `ProveItRuntime.decide` returned before
  `Ledger.record` when every finding was waived, which broke the "logged, not silent" promise.
  Every non-empty batch is now recorded; warn and escalate are still suppressed when nothing is
  open. A same-line `# proveit: intended` waiver on `assert True` was also dropped by the detector
  before it could be logged; it is now marked waived and recorded like other waivers.
- **An exact restoration clears the current warning.** After `assert True` was reverted to the
  original bytes, `pre_verify` still reported "unexplained weakening remains". Outstanding
  findings are now reconciled on every later edit to a watched file, including clean and
  strengthening edits, by re-checking against the content before the first unresolved
  weakening. Historical receipts are kept.
- **The open count spans files and batches.** `_unexplained` was overwritten per batch, so the
  footer only reflected the latest edit. Outstanding findings are now tracked per file (and for
  commands) with stable identities, so two unresolved edits in two files count as 2 and
  restoring one gives 1.

### Changed

- The slash command is renamed from `/proveit` to `/proveit-tests`.

### Known limitations

- Widened `pytest.raises(...)` expectations are not flagged yet (documented in the README).
