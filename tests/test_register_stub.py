"""register(ctx) must wire documented hooks without importing Hermes."""

from __future__ import annotations

import importlib


class FakeCtx:
    def __init__(self):
        self.hooks = []
        self.commands = []
        self.settings = {"mode": "observe"}

    def register_hook(self, name, fn, **kwargs):
        self.hooks.append((name, fn))

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands.append(name)

    def current_cron_execution(self):
        return None

    def plugin_data_dir(self):
        return "/tmp/proveit-fake-data"


def test_register_wires_expected_hooks():
    mod = importlib.import_module("__init__") if False else None
    # Load package root __init__ as the plugin module
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    # The plugin __init__.py lives at package root; import via importlib
    import importlib.util

    from conftest import load_plugin_like_hermes

    plugin = load_plugin_like_hermes("proveit_tests_plugin")

    ctx = FakeCtx()
    plugin.register(ctx)
    names = {h[0] for h in ctx.hooks}
    assert names == {
        "pre_tool_call",
        "post_tool_call",
        "transform_tool_result",
        "pre_verify",
        "on_session_start",
        "on_session_end",
    }
    assert "proveit-tests" in ctx.commands
