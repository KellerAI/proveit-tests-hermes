"""Detectors for test weakenings across Python, JS/TS, and commands."""

from .commands import detect_command_weakenings, detect_ci_weakenings
from .js_ts import detect_js_ts_diff
from .paths import is_ci_path, is_test_path
from .python_ast import detect_python_diff
from .waivers import extract_waivers, apply_waivers

__all__ = [
    "detect_command_weakenings",
    "detect_ci_weakenings",
    "detect_js_ts_diff",
    "detect_python_diff",
    "is_ci_path",
    "is_test_path",
    "extract_waivers",
    "apply_waivers",
]
