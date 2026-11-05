"""Path helpers: decide which files are tests or CI configs."""

from __future__ import annotations

import fnmatch
import os
from pathlib import PurePosixPath

DEFAULT_TEST_GLOBS = (
    "**/test_*.py",
    "**/*_test.py",
    "**/tests/**/*.py",
    "**/test/**/*.py",
    "**/*.test.js",
    "**/*.test.jsx",
    "**/*.test.ts",
    "**/*.test.tsx",
    "**/*.spec.js",
    "**/*.spec.jsx",
    "**/*.spec.ts",
    "**/*.spec.tsx",
    "**/__tests__/**",
)

DEFAULT_CI_GLOBS = (
    ".github/workflows/**",
    ".gitlab-ci.yml",
    "azure-pipelines*.yml",
    "Jenkinsfile",
    ".circleci/**",
    ".buildkite/**",
)


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def matches_any(path: str, globs: tuple[str, ...] | list[str]) -> bool:
    n = _norm(path)
    name = os.path.basename(n)
    for g in globs:
        g = g.replace("\\", "/")
        if fnmatch.fnmatch(n, g) or fnmatch.fnmatch(name, g):
            return True
        try:
            if PurePosixPath(n).match(g):
                return True
        except Exception:
            pass
        if g.startswith("**/") and (fnmatch.fnmatch(name, g[3:]) or fnmatch.fnmatch(n, g[3:])):
            return True
        if "/tests/" in f"/{n}/" and g.endswith("**/tests/**/*.py") and n.endswith(".py"):
            return True
        if "/__tests__/" in f"/{n}/" and "__tests__" in g:
            return True
    return False


def is_test_path(path: str, globs: tuple[str, ...] | list[str] | None = None) -> bool:
    return matches_any(path, globs or DEFAULT_TEST_GLOBS)


def is_ci_path(path: str, globs: tuple[str, ...] | list[str] | None = None) -> bool:
    n = _norm(path)
    if n.endswith((".yml", ".yaml")) and (
        ".github/workflows/" in n or n.startswith(".github/workflows/")
    ):
        return True
    return matches_any(path, globs or DEFAULT_CI_GLOBS)
