"""Net-new filtering for presence-style ("absolute") findings.

Absolute scanners (skip/xfail/.only, assert True, tautology, empty catch,
assertionless test, syntax error) look at one file version. Run on the new
version alone they also report weakenings that were already there before the
edit. To claim an edit *introduced* a weakening we subtract the findings the
old version already had, matched by a line-number-independent signature
(kind + message + stripped source text of the flagged line), as a multiset so
adding a second identical skip still counts as one new finding.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from ..findings import Finding


def _line_text(source: str, line: int | None) -> str:
    if not line:
        return ""
    lines = source.splitlines()
    if 1 <= line <= len(lines):
        return " ".join(lines[line - 1].split())
    return ""


def signature(f: Finding, source: str) -> tuple[str, str, str, str]:
    return (f.kind, f.message, f.detail, _line_text(source, f.line))


def net_new(
    old_findings: Iterable[Finding],
    old_source: str,
    new_findings: Iterable[Finding],
    new_source: str,
) -> list[Finding]:
    """Return the new-version findings not already present in the old version."""
    budget = Counter(signature(f, old_source) for f in old_findings)
    out: list[Finding] = []
    for f in new_findings:
        sig = signature(f, new_source)
        if budget[sig] > 0:
            budget[sig] -= 1
            continue
        out.append(f)
    return out
