"""Python AST detectors for test weakenings.

Compares old vs new source for a test file and emits Findings.
Deterministic — no LLM.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from ..findings import Finding, Severity
from .netnew import net_new
from .waivers import apply_waivers

_TEST_NAME = re.compile(r"^(test_|Test)")
_ASSERT_TRUE = re.compile(r"^\s*assert\s+True\b")
_EXPECT_LITERAL_LOOSE = re.compile(
    r"assert\s+.+\s*==\s*(.+)$|"
    r"self\.assertEqual\([^,]+,\s*(.+)\)|"
    r"self\.assertEquals\([^,]+,\s*(.+)\)",
    re.M,
)


def _is_test_func(name: str) -> bool:
    return bool(_TEST_NAME.match(name))


def _func_nodes(tree: ast.AST) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_func(node.name):
            out[node.name] = node
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_func(
                    child.name
                ):
                    out[f"{node.name}.{child.name}"] = child
    return out


def _count_asserts(node: ast.AST) -> int:
    n = 0
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            n += 1
        elif isinstance(child, ast.Call):
            func = child.func
            name = ""
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name.startswith("assert") or name in {
                "assertEqual",
                "assertEquals",
                "assertTrue",
                "assertFalse",
                "assertIn",
                "assertRaises",
                "assertAlmostEqual",
                "assertIs",
                "assertIsNone",
                "assertIsNotNone",
                "assertGreater",
                "assertLess",
            }:
                n += 1
    return n




def _module_assert_count(tree: ast.AST | None) -> int:
    if tree is None:
        return 0
    return sum(_count_asserts(node) for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))


def _looks_like_rename(
    old_funcs: dict[str, ast.AST],
    new_funcs: dict[str, ast.AST],
    removed_name: str,
) -> str | None:
    """If a deleted test has a same-assert-count newly added twin, treat as rename.

    Returns the matched new name, or None. Greedy; callers should consume matches.
    """
    if removed_name not in old_funcs:
        return None
    old_n = _count_asserts(old_funcs[removed_name])
    added = sorted(set(new_funcs) - set(old_funcs))
    for cand in added:
        if _count_asserts(new_funcs[cand]) == old_n:
            return cand
    return None

def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    names: list[str] = []
    for d in node.decorator_list:
        names.append(ast.unparse(d) if hasattr(ast, "unparse") else _deco_fallback(d))
    return names


def _deco_fallback(d: ast.AST) -> str:
    if isinstance(d, ast.Name):
        return d.id
    if isinstance(d, ast.Attribute):
        return f"{_deco_fallback(d.value)}.{d.attr}"
    if isinstance(d, ast.Call):
        return _deco_fallback(d.func)
    return type(d).__name__


def _has_skip_or_xfail(decorators: list[str]) -> list[str]:
    hits = []
    for d in decorators:
        low = d.lower()
        if "skip" in low or "xfail" in low:
            hits.append(d)
    return hits


def _has_try_except_pass(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Try):
            for handler in child.handlers:
                body = handler.body
                if len(body) == 1 and isinstance(body[0], ast.Pass):
                    return True
                if not body:
                    return True
    return False


def _assert_true_lines(source: str) -> list[int]:
    lines = []
    for i, line in enumerate(source.splitlines(), start=1):
        if _ASSERT_TRUE.search(line) and "proveit: intended" not in line.lower():
            # ignore assert True, "msg" used as documentation? still a tautology for value
            lines.append(i)
    return lines


def _literal_eq_asserts(node: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, expected_repr) for assert x == <literal> style checks."""
    out: list[tuple[int, str]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assert) and isinstance(child.test, ast.Compare):
            if len(child.test.ops) == 1 and isinstance(child.test.ops[0], (ast.Eq, ast.Is)):
                right = child.test.comparators[0]
                if isinstance(right, ast.Constant):
                    out.append((child.lineno, repr(right.value)))
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr in {"assertEqual", "assertEquals"} and len(child.args) >= 2:
                right = child.args[1]
                if isinstance(right, ast.Constant):
                    out.append((child.lineno, repr(right.value)))
    return out


def _parse(source: str) -> ast.AST | None:
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def detect_python_source(source: str, path: str = "") -> list[Finding]:
    """Single-file absolute checks (no old version needed)."""
    findings: list[Finding] = []
    tree = _parse(source)
    if tree is None:
        findings.append(
            Finding(
                kind="syntax-error-in-test",
                message="Test file no longer parses",
                severity=Severity.CRITICAL,
                path=path,
            )
        )
        return apply_waivers(findings, source)

    for name, node in _func_nodes(tree).items():
        assert_count = _count_asserts(node)
        if assert_count == 0 and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # empty or assertionless test body (allow docstring-only + pass)
            body = [b for b in node.body if not isinstance(b, (ast.Pass, ast.Expr))]
            # Expr might be docstring — already filtered if Constant str at start
            meaningful = []
            for b in node.body:
                if isinstance(b, ast.Pass):
                    continue
                if (
                    isinstance(b, ast.Expr)
                    and isinstance(b.value, ast.Constant)
                    and isinstance(b.value.value, str)
                ):
                    continue
                meaningful.append(b)
            if not meaningful or assert_count == 0:
                # only flag if the function has a body that looks like a test without asserts
                if meaningful:
                    findings.append(
                        Finding(
                            kind="assertionless-test",
                            message=f"Test {name} has no assertions",
                            severity=Severity.CRITICAL,
                            path=path,
                            line=getattr(node, "lineno", None),
                        )
                    )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            skips = _has_skip_or_xfail(_decorator_names(node))
            for s in skips:
                findings.append(
                    Finding(
                        kind="skip-or-xfail",
                        message=f"Test {name} marked {s}",
                        severity=Severity.CRITICAL,
                        path=path,
                        line=getattr(node, "lineno", None),
                        detail=s,
                    )
                )
            if _has_try_except_pass(node):
                findings.append(
                    Finding(
                        kind="try-except-pass",
                        message=f"Test {name} swallows exceptions with bare except/pass",
                        severity=Severity.CRITICAL,
                        path=path,
                        line=getattr(node, "lineno", None),
                    )
                )

    for lineno in _assert_true_lines(source):
        findings.append(
            Finding(
                kind="assert-true",
                message="Tautological assert True",
                severity=Severity.CRITICAL,
                path=path,
                line=lineno,
            )
        )

    # assert x == x / identical sides
    if tree:
        for child in ast.walk(tree):
            if isinstance(child, ast.Assert) and isinstance(child.test, ast.Compare):
                if len(child.test.ops) == 1 and isinstance(child.test.ops[0], ast.Eq):
                    left = child.test.left
                    right = child.test.comparators[0]
                    try:
                        if ast.dump(left) == ast.dump(right):
                            findings.append(
                                Finding(
                                    kind="tautology",
                                    message="Assertion compares a value to itself",
                                    severity=Severity.CRITICAL,
                                    path=path,
                                    line=child.lineno,
                                )
                            )
                    except Exception:
                        pass

    return apply_waivers(findings, source)


def detect_python_diff(old: str, new: str, path: str = "") -> list[Finding]:
    """Diff-aware checks between previous and proposed test file contents.

    Presence-style findings (skip/xfail, assert True, tautology, try/except
    pass, assertionless test, syntax error) are reported only when they are
    net-new versus ``old``: a weakening that already existed before the edit is
    not attributed to the edit. ``old == ""`` means the file is new, so every
    finding in it is new. Callers that do not know the prior content must not
    call this (see ProveItRuntime snapshots).
    """
    old_abs = detect_python_source(old, path=path) if old.strip() else []
    findings = net_new(old_abs, old, detect_python_source(new, path=path), new)

    old_tree = _parse(old) if old.strip() else None
    new_tree = _parse(new)
    if new_tree is None:
        return apply_waivers(findings, new)

    old_funcs = _func_nodes(old_tree) if old_tree else {}
    new_funcs = _func_nodes(new_tree)

    # Module-level assert stability: extract-to-helper keeps total asserts
    # but drops per-test counts — suppress removed-assert / assertionless FPs.
    old_module_asserts = _module_assert_count(old_tree)
    new_module_asserts = _module_assert_count(new_tree)
    module_asserts_stable = new_module_asserts >= old_module_asserts and old_module_asserts > 0

    if module_asserts_stable:
        findings = [
            f
            for f in findings
            if f.kind not in {"removed-assert", "assertionless-test"}
        ]

    # Deleted tests (skip rename-shaped pairs: same assert count, new name appeared)
    claimed_renames: set[str] = set()
    for name in sorted(set(old_funcs) - set(new_funcs)):
        twin = _looks_like_rename(old_funcs, new_funcs, name)
        if twin and twin not in claimed_renames:
            claimed_renames.add(twin)
            continue
        findings.append(
            Finding(
                kind="deleted-test",
                message=f"Test function removed: {name}",
                severity=Severity.CRITICAL,
                path=path,
                line=getattr(old_funcs[name], "lineno", None),
            )
        )

    # Assert count drops / expected literal changes
    for name, new_node in new_funcs.items():
        if name not in old_funcs:
            continue
        old_node = old_funcs[name]
        old_n = _count_asserts(old_node)
        new_n = _count_asserts(new_node)
        if new_n < old_n and not module_asserts_stable:
            findings.append(
                Finding(
                    kind="removed-assert",
                    message=f"Assert count in {name} dropped {old_n} → {new_n}",
                    severity=Severity.CRITICAL,
                    path=path,
                    line=getattr(new_node, "lineno", None),
                    evidence={"old": old_n, "new": new_n},
                )
            )

        old_lits = {v: ln for ln, v in _literal_eq_asserts(old_node)}
        new_lits = {v: ln for ln, v in _literal_eq_asserts(new_node)}
        # If an expected literal disappeared and a different one appeared in same test, flag rewrite
        if old_lits and new_lits and set(old_lits) != set(new_lits):
            # Heuristic: any change of expected constant in an equality assert
            removed = set(old_lits) - set(new_lits)
            added = set(new_lits) - set(old_lits)
            if removed and added:
                findings.append(
                    Finding(
                        kind="expected-literal-rewrite",
                        message=(
                            f"Expected literal in {name} rewritten "
                            f"{sorted(removed)} → {sorted(added)}"
                        ),
                        severity=Severity.CRITICAL,
                        path=path,
                        line=getattr(new_node, "lineno", None),
                        evidence={"removed": sorted(removed), "added": sorted(added)},
                    )
                )

        # Newly added skip/xfail is covered by net_new() above (pre-existing
        # skips are subtracted; a skip added in this edit stays).

    return apply_waivers(findings, new)


def summarize_test_names(source: str) -> list[str]:
    tree = _parse(source)
    if not tree:
        return []
    return sorted(_func_nodes(tree))
