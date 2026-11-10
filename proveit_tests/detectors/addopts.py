"""Classify pytest command-line options that narrow or neuter a test run.

Shared by the pytest-config detector (``addopts`` in pyproject.toml / pytest.ini /
setup.cfg / tox.ini) and the command detector (``PYTEST_ADDOPTS=...`` env
assignments). Pure string logic: deterministic, no network.
"""

from __future__ import annotations

import re
import shlex

from ..findings import Severity

_NOT_WORD = re.compile(r"(?:^|[\s(])(?:not\b|!)", re.I)

# flag -> (kind, message, takes_value)
_VALUE_FLAGS = {
    "-k": ("pytest-config-k", "pytest addopts filters tests with -k"),
    "-m": ("pytest-config-m", "pytest addopts selects tests by marker (-m)"),
    "--deselect": ("pytest-config-deselect", "pytest addopts drops tests with --deselect"),
    "--ignore": ("pytest-config-ignore", "pytest addopts skips collecting a path (--ignore)"),
    "--ignore-glob": ("pytest-config-ignore", "pytest addopts skips collecting paths (--ignore-glob)"),
}
_BARE_FLAGS = {
    "--continue-on-collection-errors": (
        "pytest-config-collection-errors-ignored",
        "pytest addopts keeps going past collection errors",
    ),
    "--collect-only": ("pytest-config-collect-only", "pytest addopts collects tests without running them"),
    "--co": ("pytest-config-collect-only", "pytest addopts collects tests without running them"),
    "--suppress-no-test-exit-code": (
        "pytest-config-pass-with-no-tests",
        "pytest addopts lets a run with zero tests exit 0",
    ),
}


def split_opts(value: str, *, comments: bool = False) -> list[str]:
    try:
        return shlex.split(value, comments=comments)
    except ValueError:
        return value.split()


def addopts_weakenings(tokens: list[str]) -> list[tuple[str, str, Severity, str]]:
    """Return ``(kind, message, severity, detail)`` for each weakening option.

    ``detail`` is the normalized option text (e.g. ``-k not slow``) and is what
    net-new comparison keys on, so an unchanged pre-existing ``-m "not slow"``
    is not re-reported while a changed expression is.
    """
    out: list[tuple[str, str, Severity, str]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        flag, val = tok, None
        if "=" in tok and tok.startswith("--"):
            flag, val = tok.split("=", 1)
        elif tok[:2] in ("-k", "-m") and len(tok) > 2:
            flag, val = tok[:2], tok[2:].lstrip("=")
        if flag in _VALUE_FLAGS:
            if val is None:
                val = tokens[i + 1] if i + 1 < len(tokens) else ""
                i += 1
            kind, message = _VALUE_FLAGS[flag]
            sev = Severity.CRITICAL
            if flag == "-m" and not _NOT_WORD.search(val):
                sev = Severity.WARNING
            if flag == "-k" and _NOT_WORD.search(val):
                message = "pytest addopts excludes tests via -k 'not' expression"
            out.append((kind, message, sev, f"{flag} {' '.join(val.split())}".strip()))
        elif flag in _BARE_FLAGS:
            kind, message = _BARE_FLAGS[flag]
            out.append((kind, message, Severity.CRITICAL, flag))
        i += 1
    return out
