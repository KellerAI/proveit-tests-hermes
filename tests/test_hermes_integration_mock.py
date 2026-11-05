"""Pure-Python integration tests mocking a minimal Hermes PluginContext.

Documents the real `hermes plugins validate` / `doctor` Gate 2 gap: these
tests exercise register() + hook callback contracts without installing Hermes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "proveit_tests_plugin_integration", ROOT / "__init__.py"
    )
    plugin = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(plugin)
    return plugin


class MockHermesCtx:
    """Minimal stand-in for Hermes PluginContext (documented public surface)."""

    def __init__(self, settings=None, *, cron=None, data_dir=None):
        self.settings = settings or {"mode": "observe"}
        self.hooks: dict[str, list] = {}
        self.commands: dict[str, object] = {}
        self.command_meta: dict[str, dict] = {}
        self._cron = cron
        self._data_dir = data_dir
        self.session_id = "sess-mock-1"

    def register_hook(self, name, fn, **kwargs):
        self.hooks.setdefault(name, []).append(fn)

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = handler
        self.command_meta[name] = {"description": description, "args_hint": args_hint}

    def current_cron_execution(self):
        return self._cron

    def plugin_data_dir(self):
        return str(self._data_dir) if self._data_dir else "/tmp/proveit-mock-data"


def test_register_observe_write_file_warns(tmp_path):
    plugin = _load_plugin()
    ctx = MockHermesCtx({"mode": "observe"}, data_dir=tmp_path)
    plugin.register(ctx)

    assert set(ctx.hooks) >= {
        "pre_tool_call",
        "post_tool_call",
        "transform_tool_result",
        "pre_verify",
        "on_session_start",
        "on_session_end",
    }
    assert "proveit" in ctx.commands

    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    weak = "def test_a():\n    assert True\n"

    pre = ctx.hooks["pre_tool_call"][0]
    transform = ctx.hooks["transform_tool_result"][0]
    directive = pre("write_file", {"path": str(path), "content": weak}, task_id="t1")
    assert directive is None  # observe never blocks/approves
    out = transform("write_file", {"path": str(path), "content": weak}, result="wrote ok")
    assert out is not None
    assert "ProveIt" in out
    assert "receipt" in out.lower() or "weakening" in out.lower() or "assert" in out.lower()

    ledger = ctx.commands["proveit"]("")
    assert "ProveIt ledger" in ledger
    assert "assert-true" in ledger or "open=" in ledger


def test_register_escalate_includes_rule_key(tmp_path):
    plugin = _load_plugin()
    ctx = MockHermesCtx({"mode": "escalate"}, data_dir=tmp_path)
    plugin.register(ctx)
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    pre = ctx.hooks["pre_tool_call"][0]
    d = pre(
        "write_file",
        {"path": str(path), "content": "def test_a():\n    assert True\n"},
        task_id="t2",
    )
    assert d is not None
    assert d["action"] == "approve"
    assert d.get("rule_key") == "proveit-tests:test-weakening"


def test_register_unattended_blocks(tmp_path):
    plugin = _load_plugin()
    cron = SimpleNamespace(job_id="job-1", job_name="nightly")
    ctx = MockHermesCtx({"mode": "block_unattended"}, cron=cron, data_dir=tmp_path)
    plugin.register(ctx)
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    pre = ctx.hooks["pre_tool_call"][0]
    d = pre(
        "terminal",
        {"command": "pytest || true"},
        task_id="t3",
    )
    assert d is not None
    assert d["action"] == "block"
    assert "unattended" in d["message"].lower() or "cron" in d["message"].lower()


def test_register_pre_verify_continue_once(tmp_path):
    plugin = _load_plugin()
    ctx = MockHermesCtx({"mode": "observe", "one_shot_nudge": True}, data_dir=tmp_path)
    plugin.register(ctx)
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    ctx.hooks["pre_tool_call"][0](
        "write_file",
        {"path": str(path), "content": "def test_a():\n    assert True\n"},
    )
    pre_verify = ctx.hooks["pre_verify"][0]
    d1 = pre_verify(changed_paths=[str(path)], attempt=0, final_response="done")
    assert d1 is not None
    assert d1.get("action") == "continue"
    d2 = pre_verify(changed_paths=[str(path)], attempt=0, final_response="done")
    assert d2 is None


def test_session_start_resets_state(tmp_path):
    plugin = _load_plugin()
    ctx = MockHermesCtx({"mode": "observe"}, data_dir=tmp_path)
    plugin.register(ctx)
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    ctx.hooks["pre_tool_call"][0](
        "write_file",
        {"path": str(path), "content": "def test_a():\n    assert True\n"},
    )
    ctx.hooks["on_session_start"][0](session_id="sess-2")
    # After reset, pre_verify should not nudge about prior session findings
    d = ctx.hooks["pre_verify"][0](changed_paths=[str(path)], attempt=0)
    assert d is None


def test_post_tool_call_rescans_disk_when_content_missing(tmp_path):
    plugin = _load_plugin()
    ctx = MockHermesCtx({"mode": "observe"}, data_dir=tmp_path)
    plugin.register(ctx)
    path = tmp_path / "test_x.py"
    # Agent wrote via a tool that did not put content in args; disk already weak
    path.write_text("def test_a():\n    assert True\n", encoding="utf-8")
    post = ctx.hooks["post_tool_call"][0]
    post("write_file", {"path": str(path)}, result="ok", duration_ms=3)
    out = ctx.hooks["transform_tool_result"][0](
        "write_file", {"path": str(path)}, result="ok"
    )
    assert out is not None
    assert "ProveIt" in out


def test_gate2_still_required_note():
    """Explicit marker test — real hermes validate/doctor needs Gate 2 install."""
    note = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    assert "Hermes-gated" in note or "Gate 2" in note or "do **not** run until" in note
    assert "hermes plugins validate" in note
    assert "hermes plugins doctor" in note
