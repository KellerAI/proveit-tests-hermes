"""Shapes taken from Hermes v0.22.7 source (found during Gate 2 real install):
- PluginContext exposes get_config(key, default), not a settings dict.
- Core `patch` tool args are path/old_string/new_string[/replace_all]."""

from __future__ import annotations

from conftest import load_plugin_like_hermes


class GetConfigCtx:
    """Only the real Hermes surface: get_config + register_*; no settings attr."""

    def __init__(self, cfg):
        self._cfg = cfg
        self.hooks = {}
        self.commands = {}

    def get_config(self, key, default=None):
        return self._cfg.get(key, default)

    def register_hook(self, name, cb):
        self.hooks[name] = cb

    def register_command(self, name, handler, description=""):
        self.commands[name] = handler

    def current_cron_execution(self):
        return None


def _tiny(tmp_path):
    t = tmp_path / "tests"
    t.mkdir()
    f = t / "test_add.py"
    f.write_text("from add import add\n\ndef test_add():\n    total = add(4, 5)\n    assert total == 9\n")
    return f


def test_get_config_mode_is_honored(tmp_path):
    plugin = load_plugin_like_hermes("proveit_tests_plugin_realsurface")
    ctx = GetConfigCtx({"mode": "escalate", "receipt_dir": str(tmp_path / "ledger")})
    plugin.register(ctx)
    f = _tiny(tmp_path)
    out = ctx.hooks["pre_tool_call"](
        "write_file", args={"path": str(f), "content": f.read_text().replace("== 9", "== 8")}
    )
    assert out and out["action"] == "approve"
    assert out["rule_key"] == "proveit-tests:test-weakening"


def test_patch_old_string_new_string_is_analyzed_pre_edit(tmp_path):
    plugin = load_plugin_like_hermes("proveit_tests_plugin_realsurface2")
    ctx = GetConfigCtx({"mode": "escalate", "receipt_dir": str(tmp_path / "ledger")})
    plugin.register(ctx)
    f = _tiny(tmp_path)
    out = ctx.hooks["pre_tool_call"](
        "patch", args={"path": str(f), "old_string": "assert total == 9", "new_string": "assert total == 8"}
    )
    assert out and out["action"] == "approve", out


def test_patch_honest_change_not_flagged(tmp_path):
    plugin = load_plugin_like_hermes("proveit_tests_plugin_realsurface3")
    ctx = GetConfigCtx({"mode": "escalate", "receipt_dir": str(tmp_path / "ledger")})
    plugin.register(ctx)
    f = _tiny(tmp_path)
    out = ctx.hooks["pre_tool_call"](
        "patch",
        args={"path": str(f), "old_string": "    assert total == 9\n", "new_string": "    assert total == 9\n    assert add(0, 0) == 0\n"},
    )
    assert out is None
