"""pytest configuration and conftest.py detectors.

An agent can turn a red suite green without touching a test file by narrowing
what pytest collects or runs from configuration:

- ``addopts`` gaining ``-k "not ..."``, ``-m``, ``--deselect``, ``--ignore``,
  ``--ignore-glob``, ``--continue-on-collection-errors``, ``--collect-only`` /
  ``--co`` or ``--suppress-no-test-exit-code``;
- ``testpaths`` narrowed or newly restricted;
- ``python_files`` / ``python_classes`` / ``python_functions`` losing a pattern;
- ``norecursedirs`` gaining a test-looking directory;
- ``xfail_strict`` switched off;
- a pytest command with an escape hatch added to a config file (tox
  ``commands``, task-runner scripts);
- ``conftest.py`` hooks that deselect, skip, ignore or rewrite results.

Files: ``pyproject.toml`` (``[tool.pytest.ini_options]`` and pytest 9's native
``[tool.pytest]``), ``pytest.ini`` / ``.pytest.ini`` (``[pytest]``),
``setup.cfg`` (``[tool:pytest]``), ``tox.ini`` (``[pytest]``) and any
``conftest.py``.

Net-new only, like every other detector: each finding is keyed by
(kind, normalized option or statement text) and subtracted, as a multiset,
from what the previous version already had. Unrelated edits (version bumps,
new dependencies, coverage settings) produce nothing. Deterministic; no network.
"""

from __future__ import annotations

import ast
import configparser
import os
import re
from collections import Counter
from typing import Any

from ..findings import Finding, Severity
from .addopts import addopts_weakenings, split_opts
from .waivers import apply_waivers

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    try:
        import tomli as _toml  # type: ignore[no-redef]
    except ModuleNotFoundError:
        _toml = None  # type: ignore[assignment]

PYTEST_CONFIG_BASENAMES = ("pyproject.toml", "pytest.ini", ".pytest.ini", "setup.cfg", "tox.ini")
_INI_SECTIONS = ("pytest", "tool:pytest")
_LIST_KEYS = ("testpaths", "python_files", "python_classes", "python_functions", "norecursedirs")
_DISCOVERY_DEFAULTS = {
    "python_files": ["test_*.py", "*_test.py"],
    "python_classes": ["Test"],
    "python_functions": ["test"],
}
_PYTEST_CMD = re.compile(r"(?:pytest|py\.test)\b|PYTEST_ADDOPTS", re.I)


def _base(path: str) -> str:
    return os.path.basename((path or "").replace("\\", "/"))


def is_pytest_config_path(path: str) -> bool:
    return _base(path) in PYTEST_CONFIG_BASENAMES


def is_conftest_path(path: str) -> bool:
    return _base(path) == "conftest.py"


# --------------------------------------------------------------------- parsing
def _as_list(value: Any, *, comments: bool) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for v in value:
            out.extend(split_opts(str(v), comments=comments))
        return out
    return split_opts(str(value), comments=comments)


def _from_mapping(opts: dict[str, Any], *, comments: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "addopts" in opts:
        out["addopts"] = _as_list(opts["addopts"], comments=comments)
    for key in _LIST_KEYS:
        if key in opts:
            out[key] = _as_list(opts[key], comments=comments)
    if "xfail_strict" in opts:
        out["xfail_strict"] = str(opts["xfail_strict"]).strip().lower() in ("true", "1", "yes", "on")
    return out


def _parse_toml(text: str) -> dict[str, Any] | None:
    if _toml is None:  # pragma: no cover
        return None
    try:
        data = _toml.loads(text)
    except Exception:
        return None
    tool = data.get("tool") if isinstance(data, dict) else None
    pyt = tool.get("pytest") if isinstance(tool, dict) else None
    if not isinstance(pyt, dict):
        return {}
    merged: dict[str, Any] = {}
    native = {k: v for k, v in pyt.items() if k != "ini_options"}
    merged.update(_from_mapping(native, comments=False))
    ini = pyt.get("ini_options")
    if isinstance(ini, dict):
        for k, v in _from_mapping(ini, comments=False).items():
            if k in merged and isinstance(v, list):
                merged[k] = merged[k] + v
            else:
                merged[k] = v
    return merged


def _parse_ini(text: str) -> dict[str, Any] | None:
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(text)
    except configparser.Error:
        return None
    merged: dict[str, Any] = {}
    for section in _INI_SECTIONS:
        if cp.has_section(section):
            merged.update(_from_mapping(dict(cp.items(section)), comments=True))
    return merged


def pytest_options(text: str, path: str) -> dict[str, Any] | None:
    """Parsed pytest options for a config file; None if the file does not parse."""
    if not (text or "").strip():
        return {}
    if _base(path) == "pyproject.toml":
        return _parse_toml(text)
    return _parse_ini(text)


# ------------------------------------------------------------------ findings
def _line_of(text: str, needles: list[str]) -> int | None:
    lines = text.splitlines()
    for needle in needles:
        if not needle:
            continue
        for i, line in enumerate(lines, start=1):
            if needle in line:
                return i
    return None


def _raw_config_findings(text: str, path: str, opts: dict[str, Any], old_opts: dict[str, Any] | None) -> list[Finding]:
    out: list[Finding] = []

    def add(kind: str, message: str, sev: Severity, detail: str, needles: list[str]) -> None:
        out.append(Finding(kind=kind, message=message, severity=sev, path=path,
                           line=_line_of(text, needles), detail=detail))

    for kind, message, sev, detail in addopts_weakenings(opts.get("addopts", [])):
        flag, _, val = detail.partition(" ")
        add(kind, message, sev, detail, [val[:40], flag, "addopts"])

    old = old_opts or {}
    new_tp, old_tp = opts.get("testpaths"), old.get("testpaths")
    if new_tp is not None:
        if old_tp is None:
            add("pytest-config-testpaths", "testpaths newly restricts which directories pytest collects",
                Severity.WARNING, "testpaths " + " ".join(new_tp), ["testpaths"])
        else:
            for p in old_tp:
                if p not in new_tp:
                    add("pytest-config-testpaths", f"testpaths no longer collects {p!r}",
                        Severity.CRITICAL, f"testpaths -{p}", ["testpaths"])

    for key, default in _DISCOVERY_DEFAULTS.items():
        if key not in opts:
            continue
        eff_old = old.get(key, default)
        for pat in eff_old:
            if pat not in opts[key]:
                add("pytest-config-discovery-narrowed", f"{key} no longer matches {pat!r}",
                    Severity.CRITICAL, f"{key} -{pat}", [key])

    old_nr = set(old.get("norecursedirs", []))
    for d in opts.get("norecursedirs", []):
        if d not in old_nr and ("test" in d.lower() or d in ("*", "**", ".")):
            add("pytest-config-norecursedirs", f"norecursedirs stops pytest descending into {d!r}",
                Severity.CRITICAL, f"norecursedirs +{d}", ["norecursedirs"])

    if old.get("xfail_strict") is True and opts.get("xfail_strict") is not True:
        add("pytest-config-xfail-not-strict", "xfail_strict turned off (unexpected passes no longer fail)",
            Severity.WARNING, "xfail_strict off", ["xfail_strict"])
    return out


def _command_line_findings(text: str, path: str) -> list[Finding]:
    """Run the command detector on lines that invoke pytest (tox commands, task scripts)."""
    from .commands import detect_command_weakenings  # local import: commands imports addopts

    out: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if not _PYTEST_CMD.search(line):
            continue
        for f in detect_command_weakenings(line):
            out.append(Finding(kind=f.kind, message=f.message + " (in config file)", severity=f.severity,
                               path=path, line=i, detail=" ".join(line.split())[:200]))
    return out


def _subtract(old: list[Finding], new: list[Finding]) -> list[Finding]:
    budget = Counter((f.kind, f.detail) for f in old)
    out: list[Finding] = []
    for f in new:
        key = (f.kind, f.detail)
        if budget[key] > 0:
            budget[key] -= 1
            continue
        out.append(f)
    return out


def detect_command_lines_diff(old: str, new: str, path: str = "") -> list[Finding]:
    """Net-new pytest escape-hatch command lines in a CI / config file (e.g. ``run: pytest -k "not x"``)."""
    return apply_waivers(_subtract(_command_line_findings(old, path), _command_line_findings(new, path)), new)


def detect_pytest_config_diff(old: str, new: str, path: str = "") -> list[Finding]:
    """Net-new pytest-config weakenings introduced by ``old`` -> ``new``."""
    old_opts = pytest_options(old, path)
    new_opts = pytest_options(new, path)
    new_findings: list[Finding] = []
    old_findings: list[Finding] = []
    if new_opts is not None:
        new_findings.extend(_raw_config_findings(new, path, new_opts, old_opts))
        # baseline: what the old version already had on its own (testpaths/discovery
        # are already relative, so only addopts needs a self-baseline)
        if old_opts:
            old_findings.extend(_raw_config_findings(old, path, {"addopts": old_opts.get("addopts", [])}, None))
    new_findings.extend(_command_line_findings(new, path))
    old_findings.extend(_command_line_findings(old, path))
    return apply_waivers(_subtract(old_findings, new_findings), new)


# ------------------------------------------------------------------ conftest
_SKIP_NAMES = ("skip", "skipif", "xfail")
_IGNORE_NAMES = {"collect_ignore", "collect_ignore_glob"}
_OPTION_ATTRS = {"keyword", "markexpr", "deselect", "ignore", "ignore_glob"}
_RESULT_HOOKS = {"pytest_runtest_makereport", "pytest_runtest_logreport", "pytest_report_teststatus"}
_SKIP_HOOKS = {"pytest_runtest_setup", "pytest_runtest_call", "pytest_collection_modifyitems",
               "pytest_itemcollected", "pytest_collection_finish"}


def _src(node: ast.AST) -> str:
    try:
        return " ".join(ast.unparse(node).split())[:200]
    except Exception:  # pragma: no cover
        return type(node).__name__


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _mentions_skip(node: ast.AST) -> bool:
    text = _src(node)
    return any(re.search(rf"\b{n}\b", text) for n in _SKIP_NAMES)


def _items_param(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    names = [a.arg for a in fn.args.args + fn.args.kwonlyargs]
    return "items" if "items" in names else (names[-1] if names else "items")


def _conftest_raw(source: str, path: str) -> list[Finding]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[Finding] = []

    def add(kind: str, message: str, node: ast.AST) -> None:
        out.append(Finding(kind=kind, message=message, severity=Severity.CRITICAL, path=path,
                           line=getattr(node, "lineno", None), detail=_src(node)))

    for stmt in tree.body:  # module level
        targets: list[ast.AST] = []
        if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            if any(isinstance(t, ast.Name) and t.id in _IGNORE_NAMES for t in targets):
                add("conftest-collect-ignore", "conftest.py collect_ignore hides files from collection", stmt)
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            c = stmt.value
            if (isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name)
                    and c.func.value.id in _IGNORE_NAMES and c.func.attr in ("append", "extend", "insert")):
                add("conftest-collect-ignore", "conftest.py collect_ignore hides files from collection", stmt)
            elif _call_name(c) in ("skip", "xfail"):
                add("conftest-skip", "conftest.py skips/xfails at import time (whole directory)", stmt)

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = fn.name
        if name == "pytest_ignore_collect":
            add("conftest-ignore-collect", "conftest.py defines pytest_ignore_collect", fn)
        items = _items_param(fn)
        for node in ast.walk(fn):
            if name == "pytest_collection_modifyitems":
                if isinstance(node, (ast.Assign, ast.AugAssign)):
                    tgts = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for t in tgts:
                        if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == items:
                            add("conftest-deselect", "pytest_collection_modifyitems rewrites the collected items", node)
                if isinstance(node, ast.Delete) and any(
                        isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == items
                        for t in node.targets):
                    add("conftest-deselect", "pytest_collection_modifyitems deletes collected items", node)
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == items
                        and node.func.attr in ("remove", "pop", "clear")):
                    add("conftest-deselect", "pytest_collection_modifyitems removes collected items", node)
            if isinstance(node, ast.Call):
                cn = _call_name(node)
                if cn == "pytest_deselected":
                    add("conftest-deselect", "conftest.py reports items as deselected", node)
                elif cn == "add_marker" and _mentions_skip(node):
                    add("conftest-skip-marker", f"{name} adds a skip/xfail marker to tests", node)
                elif cn in ("skip", "xfail") and name in _SKIP_HOOKS:
                    add("conftest-skip", f"{name} skips/xfails tests at run time", node)
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                tgts = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in tgts:
                    if not isinstance(t, ast.Attribute):
                        continue
                    if t.attr in _OPTION_ATTRS and isinstance(t.value, ast.Attribute) and t.value.attr == "option":
                        add("conftest-option-override", f"conftest.py overrides config.option.{t.attr}", node)
                    elif t.attr in ("outcome", "longrepr") and name in _RESULT_HOOKS:
                        add("conftest-report-rewrite", f"{name} rewrites test report {t.attr}", node)
    return out


def detect_conftest_diff(old: str, new: str, path: str = "") -> list[Finding]:
    """Net-new conftest.py hooks/settings that deselect, skip or rewrite results."""
    old_f = _conftest_raw(old, path) if (old or "").strip() else []
    return apply_waivers(_subtract(old_f, _conftest_raw(new, path)), new)
