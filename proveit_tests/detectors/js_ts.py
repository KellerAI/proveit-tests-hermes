"""JS/TS heuristic detectors (regex-based — limited, not AST-complete).

README must state Python-strong / JS-TS-limited. These patterns catch common
Jest/Vitest/Mocha weakenings but will miss clever or typed variants.
"""

from __future__ import annotations

import re

from ..findings import Finding, Severity
from .netnew import net_new
from .waivers import apply_waivers

_SKIP = re.compile(
    r"\b(?:it|test|describe|xit|xdescribe)\.skip\s*\(|"
    r"\bx(?:it|describe)\s*\(|"
    r"\b(?:it|test|describe)\.only\s*\(",
    re.M,
)
_EXPECT_TRUE = re.compile(r"\bexpect\s*\(\s*true\s*\)\s*\.\s*toBe(?:Truthy)?\s*\(", re.M)
_EXPECT_TRUE2 = re.compile(r"\bexpect\s*\(\s*true\s*\)\s*\.\s*toBe\s*\(\s*true\s*\)", re.M)
_REMOVED_EXPECT_HINT = re.compile(r"^\s*//\s*expect\b|^\s*/\*\s*expect\b", re.M)
_TEST_FN = re.compile(
    # it/test/describe, focused/skipped variants (.only/.skip/xit) keep the same case name
    r"\b(?:x?(?:it|test|describe))(?:\.(?:only|skip|todo|concurrent))?\s*\(\s*([`'\"])(.+?)\1",
    re.M,
)
_ASSERT_TRUE_JS = re.compile(r"\bassert\s*\(\s*true\s*[,)]", re.M)
_TRY_CATCH_EMPTY = re.compile(
    r"try\s*\{[\s\S]*?\}\s*catch\s*(?:\([^)]*\))?\s*\{\s*\}",
    re.M,
)


def _line_of(text: str, idx: int) -> int:
    return text[:idx].count("\n") + 1


def detect_js_ts_source(source: str, path: str = "") -> list[Finding]:
    findings: list[Finding] = []
    for m in _SKIP.finditer(source):
        kind = "js-only" if ".only" in m.group(0) else "js-skip"
        findings.append(
            Finding(
                kind=kind,
                message=f"JS/TS test focus/skip: {m.group(0).strip()[:60]}",
                severity=Severity.CRITICAL,
                path=path,
                line=_line_of(source, m.start()),
            )
        )
    for pat, kind, msg in (
        (_EXPECT_TRUE, "js-expect-true", "expect(true) tautology"),
        (_EXPECT_TRUE2, "js-expect-true", "expect(true).toBe(true) tautology"),
        (_ASSERT_TRUE_JS, "js-assert-true", "assert(true) tautology"),
    ):
        for m in pat.finditer(source):
            findings.append(
                Finding(
                    kind=kind,
                    message=msg,
                    severity=Severity.CRITICAL,
                    path=path,
                    line=_line_of(source, m.start()),
                )
            )
    for m in _TRY_CATCH_EMPTY.finditer(source):
        findings.append(
            Finding(
                kind="js-empty-catch",
                message="Empty catch swallows test failures",
                severity=Severity.CRITICAL,
                path=path,
                line=_line_of(source, m.start()),
            )
        )
    return apply_waivers(findings, source)


def detect_js_ts_diff(old: str, new: str, path: str = "") -> list[Finding]:
    """Presence-style findings are reported only when net-new versus ``old``."""
    old_abs = detect_js_ts_source(old, path=path) if (old or "").strip() else []
    findings = net_new(old_abs, old or "", detect_js_ts_source(new, path=path), new)

    old_names = {m.group(2) for m in _TEST_FN.finditer(old or "")}
    new_names = {m.group(2) for m in _TEST_FN.finditer(new or "")}
    for name in sorted(old_names - new_names):
        findings.append(
            Finding(
                kind="js-deleted-test",
                message=f"JS/TS test case removed: {name!r}",
                severity=Severity.CRITICAL,
                path=path,
            )
        )

    old_expects = len(re.findall(r"\bexpect\s*\(", old or ""))
    new_expects = len(re.findall(r"\bexpect\s*\(", new or ""))
    if old and new_expects < old_expects:
        findings.append(
            Finding(
                kind="js-removed-expect",
                message=f"expect() count dropped {old_expects} → {new_expects}",
                severity=Severity.CRITICAL,
                path=path,
                evidence={"old": old_expects, "new": new_expects},
            )
        )

    # Expected literal rewrite heuristic: look for changed toEqual/toBe string/number literals
    lit_re = re.compile(
        r"\.(?:toBe|toEqual|toStrictEqual)\s*\(\s*(['\"`])(.*?)\1\s*\)|"
        r"\.(?:toBe|toEqual|toStrictEqual)\s*\(\s*(-?\d+(?:\.\d+)?)\s*\)",
        re.M,
    )
    old_lits = {m.group(0) for m in lit_re.finditer(old or "")}
    new_lits = {m.group(0) for m in lit_re.finditer(new or "")}
    if old_lits and new_lits and old_lits != new_lits:
        removed = old_lits - new_lits
        added = new_lits - old_lits
        if removed and added:
            findings.append(
                Finding(
                    kind="js-expected-literal-rewrite",
                    message="JS/TS expected literal appears rewritten",
                    severity=Severity.CRITICAL,
                    path=path,
                    detail=f"removed={sorted(removed)[:3]} added={sorted(added)[:3]}",
                )
            )

    return apply_waivers(findings, new)
