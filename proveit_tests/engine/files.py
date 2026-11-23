"""Shared watched-file dispatch for edits and Git comparisons."""

from pathlib import Path

from ..detectors.commands import detect_ci_diff
from ..detectors.js_ts import detect_js_ts_diff
from ..detectors.paths import is_ci_path, is_test_path
from ..detectors.python_ast import detect_python_diff
from ..detectors.pytest_config import (
    detect_command_lines_diff,
    detect_conftest_diff,
    detect_pytest_config_diff,
    is_conftest_path,
    is_pytest_config_path,
)
from ..findings import Finding


class FileAnalyzer:
    def __init__(self, test_globs: list[str] | None = None, ci_globs: list[str] | None = None):
        self.test_globs = test_globs
        self.ci_globs = ci_globs

    def analyze_file_change(self, path: str, old: str, new: str) -> list[Finding]:
        findings: list[Finding] = []
        if is_test_path(path, self.test_globs):
            ext = Path(path).suffix.lower()
            if ext == ".py":
                findings.extend(detect_python_diff(old, new, path=path))
            elif ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
                findings.extend(detect_js_ts_diff(old, new, path=path))
        if is_ci_path(path, self.ci_globs):
            findings.extend(detect_ci_diff(old, new, path=path))
            findings.extend(detect_command_lines_diff(old, new, path=path))
        if is_pytest_config_path(path):
            findings.extend(detect_pytest_config_diff(old, new, path=path))
        if is_conftest_path(path):
            findings.extend(detect_conftest_diff(old, new, path=path))
        return findings

    def is_watched_path(self, path: str) -> bool:
        """Test files, CI configs, pytest config files, and conftest.py."""
        return (
            is_test_path(path, self.test_globs)
            or is_ci_path(path, self.ci_globs)
            or is_pytest_config_path(path)
            or is_conftest_path(path)
        )
