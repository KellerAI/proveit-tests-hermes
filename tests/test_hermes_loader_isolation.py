"""Regression (Gate 2, real `hermes plugins validate`): Hermes loads the plugin
as a package without adding the plugin dir to sys.path. An absolute
`from proveit_tests...` import in __init__.py fails there with
"No module named 'proveit_tests'". Reproduce that loader in an isolated
interpreter (-I: no cwd / PYTHONPATH on sys.path) so tests cannot pass on a
sys.path accident."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = r'''
import importlib.util, sys, types
root = sys.argv[1]
assert root not in sys.path
ns = types.ModuleType("hermes_plugins"); ns.__path__ = []; sys.modules["hermes_plugins"] = ns
name = "hermes_plugins.proveit_tests"
spec = importlib.util.spec_from_file_location(name, root + "/__init__.py", submodule_search_locations=[root])
mod = importlib.util.module_from_spec(spec); mod.__package__ = name; mod.__path__ = [root]; sys.modules[name] = mod
spec.loader.exec_module(mod)
hooks, cmds = [], []
class Ctx:
    settings = {"mode": "observe"}
    def register_hook(self, n, cb): hooks.append(n)
    def register_command(self, n, h, description=""): cmds.append(n)
mod.register(Ctx())
assert "proveit-tests" in cmds and "pre_tool_call" in hooks, (hooks, cmds)
print("ok", sorted(hooks), cmds)
'''


def test_plugin_loads_without_plugin_dir_on_sys_path(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _SCRIPT, str(ROOT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("ok")
