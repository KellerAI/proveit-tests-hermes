"""Python AST detectors for test weakenings.

Compares old vs new source for a test file and emits Findings.
Deterministic — no LLM.
"""

from __future__ import annotations

import ast
import re

from ..findings import Finding, Severity
from .netnew import net_new
from .waivers import apply_waivers

_TEST_NAME = re.compile(r"^(test_|Test)")
_ASSERT_TRUE = re.compile(r"^\s*assert\s+True\b")


def _is_test_func(name: str) -> bool:
    return bool(_TEST_NAME.match(name))


def _func_nodes(tree: ast.AST) -> dict[str, ast.AST]:
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_func(node.name):
            out[node.name] = node
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_test_func(child.name):
                    out[f"{node.name}.{child.name}"] = child
    return out


def _count_asserts(node: ast.AST) -> int:
    return len(_checks(node))


def _module_assert_count(tree: ast.AST | None) -> int:
    return len(_checks(tree)) if tree is not None else 0


def _checks(node: ast.AST) -> list[ast.Assert | ast.Call]:
    checks = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            checks.append(child)
        elif isinstance(child, ast.Call):
            name = getattr(child.func, "attr", getattr(child.func, "id", ""))
            if name.startswith("assert") or _raises(child):
                checks.append(child)
    return sorted(checks, key=lambda check: (check.lineno, check.col_offset))


def _raises(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "raises"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
    )


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    return [
        ast.unparse(decorator.func if isinstance(decorator, ast.Call) else decorator)
        for decorator in node.decorator_list
    ]


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
        if _ASSERT_TRUE.search(line):
            # Same-line `# proveit: intended` waivers are applied by
            # apply_waivers (marked waived and logged), not dropped here.
            lines.append(i)
    return lines


def _shape(node: ast.AST):
    if isinstance(node, ast.Constant):
        return ast.Constant, "_"
    return type(node), tuple(
        _shape(value) if isinstance(value, ast.AST)
        else tuple(_shape(item) if isinstance(item, ast.AST) else item for item in value)
        if isinstance(value, list) else value
        for _, value in ast.iter_fields(node)
    )


def _comparison(check: ast.AST) -> ast.cmpop | None:
    if isinstance(check, ast.Assert) and isinstance(check.test, ast.Compare):
        if len(check.test.ops) == 1:
            return check.test.ops[0]
    return None


def _strong(check: ast.AST) -> bool:
    if isinstance(_comparison(check), (ast.Eq, ast.Is)):
        return True
    return isinstance(check, ast.Call) and (
        _raises(check) or getattr(check.func, "attr", "") in {"assertEqual", "assertEquals", "assertRaises"}
    )


def _exception_types(check: ast.Call) -> set[str]:
    if not check.args:
        return set()
    arg = check.args[0]
    return {ast.unparse(item) for item in (arg.elts if isinstance(arg, ast.Tuple) else [arg])}


def _change_kind(old: ast.AST, new: ast.AST, renamed: bool) -> str | None:
    if _strong(old) and not _strong(new):
        return "assertion-weakened"
    if _raises(old) and _raises(new):
        before, after = _exception_types(old), _exception_types(new)
        if before < after or (after - before) & {
            "Exception", "BaseException", "builtins.Exception", "builtins.BaseException"
        }:
            return "assertion-weakened"
        expected_change = (
            before != after and len(before) == len(after) == 1
            and ast.dump(ast.Tuple(elts=old.args[1:] + old.keywords))
            == ast.dump(ast.Tuple(elts=new.args[1:] + new.keywords))
        )
    else:
        expected_change = _strong(old) and _shape(old) == _shape(new)
    if expected_change and ast.dump(old) != ast.dump(new):
        return "renamed-test-changed-expectation" if renamed else "expected-value-changed"
    return None


def _renamed_shape(node: ast.AST):
    # Compare the whole function, ignoring its name and normalizing checks.
    body = ast.parse(ast.unparse(node)).body[0].body
    for statement in ast.walk(ast.Module(body=body)):
        if isinstance(statement, ast.Assert):
            statement.test = ast.Constant("_")
        elif _raises(statement):
            statement.args = []
    return (
        type(node), ast.dump(node.args), tuple(map(ast.dump, node.decorator_list)),
        tuple(map(ast.dump, body)),
    )


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

    pairs = [(name, name) for name in sorted(old_funcs.keys() & new_funcs.keys())]
    added = set(new_funcs) - set(old_funcs)
    for name in sorted(set(old_funcs) - set(new_funcs)):
        old_node = old_funcs[name]
        twin = next(
            (candidate for candidate in sorted(added)
             if _renamed_shape(old_node) == _renamed_shape(new_funcs[candidate])),
            None,
        )
        if twin is not None:
            pairs.append((name, twin))
            added.remove(twin)
        else:
            findings.append(Finding(
                kind="deleted-test", message=f"Test function removed: {name}",
                severity=Severity.CRITICAL, path=path, line=old_node.lineno,
            ))

    messages = {
        "assertion-weakened": "Assertion weakened",
        "renamed-test-changed-expectation": "Expected value changed in renamed test",
        "expected-value-changed": "Expected value changed",
    }
    for old_name, name in pairs:
        old_checks = _checks(old_funcs[old_name])
        new_checks = _checks(new_funcs[name])
        old_n, new_n = len(old_checks), len(new_checks)
        if new_n < old_n and not module_asserts_stable:
            findings.append(Finding(
                kind="removed-assert", message=f"Assert count in {name} dropped {old_n} → {new_n}",
                severity=Severity.CRITICAL, path=path, line=new_funcs[name].lineno,
                evidence={"old": old_n, "new": new_n},
            ))

        # Ignore unchanged checks before pairing replacements.
        old_remaining = list(old_checks)
        new_remaining = []
        for check in new_checks:
            match = next((i for i, old_check in enumerate(old_remaining)
                          if ast.dump(old_check) == ast.dump(check)), None)
            if match is None:
                new_remaining.append(check)
            else:
                old_remaining.pop(match)
        for before, after in zip(old_remaining, new_remaining):
            kind = _change_kind(before, after, old_name != name)
            if kind == "assertion-weakened" and any(
                f.line == after.lineno and f.kind in {"assert-true", "tautology"} for f in findings
            ):
                continue
            if kind == "expected-value-changed" and old_n != new_n:
                continue
            if kind:
                findings.append(Finding(
                    kind=kind, message=f"{messages[kind]} in {name}",
                    severity=Severity.WARNING if kind == "expected-value-changed" else Severity.CRITICAL,
                    path=path, line=after.lineno,
                ))

    return apply_waivers(findings, new)


def summarize_test_names(source: str) -> list[str]:
    tree = _parse(source)
    if not tree:
        return []
    return sorted(_func_nodes(tree))
