"""Peter rule-13 should-fixes: receipt_dir confinement, no /tmp fallback, command redaction."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from proveit_tests.detectors.commands import detect_command_weakenings, redact_command
from proveit_tests.hooks.runtime import ProveItRuntime
from proveit_tests.modes import Mode
from proveit_tests.receipts.ledger import Ledger, resolve_ledger_dir

from conftest import load_plugin_like_hermes


class GetConfigCtx:
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


# ---------------------------------------------------------------- receipt_dir
def test_default_is_plugin_data_root(tmp_path):
    assert resolve_ledger_dir(tmp_path, "") == str(tmp_path)


def test_relative_override_is_confined_under_root(tmp_path):
    out = resolve_ledger_dir(tmp_path, "receipts/sub")
    assert out == str((tmp_path / "receipts" / "sub").resolve())


def test_absolute_override_rejected(tmp_path, caplog):
    outside = tmp_path.parent / "elsewhere"
    out = resolve_ledger_dir(tmp_path / "root", str(outside))
    assert out == str(tmp_path / "root")
    assert "rejected" in caplog.text


def test_home_override_rejected(tmp_path):
    assert resolve_ledger_dir(tmp_path, "~/ledger") == str(tmp_path)


def test_dotdot_escape_rejected(tmp_path, caplog):
    root = tmp_path / "root"
    root.mkdir()
    assert resolve_ledger_dir(root, "../../etc") == str(root)
    assert "escapes" in caplog.text


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    assert resolve_ledger_dir(root, "link") == str(root)
    assert not (outside / "receipts.jsonl").exists()


def test_override_without_root_is_in_memory(caplog):
    assert resolve_ledger_dir(None, "/anywhere") is None
    assert "in-memory" in caplog.text


class RootCtx(GetConfigCtx):
    def __init__(self, cfg, root):
        super().__init__(cfg)
        self._root = root

    def plugin_data_dir(self):
        return str(self._root)


def test_register_never_writes_outside_plugin_data_dir(tmp_path):
    root = tmp_path / "plugin-data"
    outside = tmp_path / "outside-ledger"
    plugin = load_plugin_like_hermes("proveit_tests_plugin_confine")
    ctx = RootCtx({"mode": "escalate", "receipt_dir": str(outside)}, root)
    plugin.register(ctx)
    f = _tiny(tmp_path)
    out = ctx.hooks["pre_tool_call"](
        "write_file", args={"path": str(f), "content": f.read_text().replace("== 9", "== 8")}
    )
    assert out and out["action"] == "approve"
    assert not outside.exists()
    assert (root / "receipts.jsonl").exists()


# ------------------------------------------------------------ no /tmp fallback
def test_runtime_without_dir_is_in_memory_not_tmp(tmp_path, caplog):
    tmp_ledger = Path(tempfile.gettempdir()) / "proveit-tests-ledger"
    before = tmp_ledger.exists()
    rt = ProveItRuntime(mode=Mode.ESCALATE)
    assert rt.ledger.persistent is False
    assert rt.ledger.path is None
    assert "in-memory" in caplog.text
    rt.decide(detect_command_weakenings("pytest || true"))
    assert len(rt.ledger.all()) == 1
    assert "in-memory only" in rt.slash_proveit()
    assert tmp_ledger.exists() == before


def test_register_without_data_dir_is_in_memory(tmp_path):
    plugin = load_plugin_like_hermes("proveit_tests_plugin_nodatadir")
    ctx = GetConfigCtx({"mode": "escalate"})
    plugin.register(ctx)
    assert "in-memory only" in ctx.commands["proveit-tests"]("")


def test_ledger_files_are_owner_only(tmp_path):
    d = tmp_path / "led"
    led = Ledger(d)
    led.record(detect_command_weakenings("pytest || true"))
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(led.path).st_mode) == 0o600


# ------------------------------------------------------------------ redaction
def test_redacts_env_secret_assignment():
    out = redact_command("GITHUB_TOKEN=abc123secret pytest -k 'not slow'")
    assert "abc123secret" not in out and "[REDACTED]" in out
    assert "pytest" in out


def test_redacts_flags_urls_bearer_and_known_tokens():
    tok = "ghp_" + "A" * 36
    cmd = (
        f"curl -H 'Authorization: Bearer zzzsecretzzz' https://bob:hunter2@example.com "
        f"--password=pw123 --api-key KEY999 {tok} && pytest || true"
    )
    out = redact_command(cmd, max_len=1000)
    for leak in ("zzzsecretzzz", "hunter2", "pw123", "KEY999", tok):
        assert leak not in out, leak
    assert "pytest || true" in out


def test_redacts_long_opaque_strings_but_keeps_paths():
    blob = "Zx9" * 15
    out = redact_command(f"pytest tests/test_very_long_module_name_here.py {blob}")
    assert blob not in out
    assert "tests/test_very_long_module_name_here.py" in out


def test_truncates_after_redaction():
    out = redact_command("pytest " + "x " * 500)
    assert len(out) <= 200


def test_command_finding_detail_is_redacted():
    fs = detect_command_weakenings("API_KEY=s3cr3tvalue pytest || true")
    assert fs and all("s3cr3tvalue" not in f.detail for f in fs)
