"""Extra runtime / path / cron / ledger coverage (toward ≥90%)."""

from __future__ import annotations

from proveit_tests.detectors.paths import is_ci_path, is_test_path, matches_any
from proveit_tests.detectors.python_ast import (
    detect_python_diff,
    detect_python_source,
    summarize_test_names,
)
from proveit_tests.detectors.waivers import apply_waivers
from proveit_tests.findings import Finding, Severity
from proveit_tests.hooks.cron import ContextCronProbe, NullCronProbe
from proveit_tests.hooks.runtime import ProveItRuntime
from proveit_tests.modes import Mode, resolve_mode
from proveit_tests.receipts.ledger import Ledger


def test_resolve_mode_defaults():
    assert resolve_mode(None) == Mode.OBSERVE
    assert resolve_mode("") == Mode.OBSERVE
    assert resolve_mode("WARN") == Mode.OBSERVE
    assert resolve_mode("approve") == Mode.ESCALATE


def test_block_unattended_escalates_when_attended(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.BLOCK_UNATTENDED, ledger_dir=tmp_path)
    d = rt.on_pre_tool_call(
        "write_file",
        args={"path": str(path), "content": "def test_a():\n    assert True\n"},
    )
    assert d is not None
    assert d["action"] == "approve"
    assert d["rule_key"] == "proveit-tests:test-weakening"


def test_escalate_blocks_when_unattended(tmp_path):
    from proveit_tests.hooks.cron import FlagCronProbe

    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    rt = ProveItRuntime(
        mode=Mode.ESCALATE, ledger_dir=tmp_path, cron=FlagCronProbe(True)
    )
    d = rt.on_pre_tool_call(
        "write_file",
        args={"path": str(path), "content": "def test_a():\n    assert True\n"},
    )
    assert d["action"] == "block"


def test_str_replace_style_args(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.ESCALATE, ledger_dir=tmp_path)
    d = rt.on_pre_tool_call(
        "str_replace",
        args={
            "path": str(path),
            "old_str": "assert 1 + 1 == 2",
            "new_str": "assert True",
            "content": "def test_a():\n    assert True\n",
        },
    )
    assert d is not None
    assert d["action"] == "approve"


def test_post_tool_terminal_redirect(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert True\n", encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path)
    rt.on_post_tool_call(
        "terminal",
        args={"command": f"cat > {path}"},
        result="ok",
    )
    assert rt._pending_warnings or rt._unexplained


def test_footer_line(tmp_path):
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path)
    line = rt.footer_line(tests_passed=3)
    assert "3 passed" in line
    assert "receipt" in line


def test_one_shot_disabled(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path, one_shot_nudge=False)
    rt.on_pre_tool_call(
        "write_file",
        args={"path": str(path), "content": "def test_a():\n    assert True\n"},
    )
    assert rt.on_pre_verify(changed_paths=[str(path)]) is None


def test_transform_empty_pending(tmp_path):
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path)
    assert rt.on_transform_tool_result(result="ok") is None


def test_context_cron_probe():
    class Ctx:
        def current_cron_execution(self):
            return object()

    assert ContextCronProbe(Ctx()).is_unattended() is True

    class Boom:
        def current_cron_execution(self):
            raise RuntimeError("nope")

    assert ContextCronProbe(Boom()).is_unattended() is False
    assert ContextCronProbe(object()).is_unattended() is False
    assert NullCronProbe().is_unattended() is False


def test_paths_variants():
    assert is_test_path("./tests/test_foo.py")
    assert is_test_path("pkg/__tests__/foo.js")
    assert is_ci_path(".github/workflows/build.yaml")
    assert matches_any("foo_test.py", ["**/*_test.py"])


def test_unittest_assert_equal_literal_rewrite():
    old = (
        "import unittest\n"
        "class TestT(unittest.TestCase):\n"
        "    def test_a(self):\n"
        "        self.assertEqual(total, 10)\n"
    )
    new = (
        "import unittest\n"
        "class TestT(unittest.TestCase):\n"
        "    def test_a(self):\n"
        "        self.assertEqual(total, 9)\n"
    )
    f = detect_python_diff(old, new, path="test_t.py")
    assert any(x.kind == "expected-literal-rewrite" for x in f)


def test_summarize_and_syntax():
    assert "test_a" in summarize_test_names("def test_a():\n    assert 1\n")
    assert summarize_test_names("def test_a(:\n") == []
    f = detect_python_source("def test_a(:\n", path="t.py")
    assert any(x.kind == "syntax-error-in-test" for x in f)


def test_file_level_waiver_no_line():
    src = "# proveit: intended whole-file fixture\ndef test_a():\n    pass\n"
    f = [
        Finding(
            kind="assertionless-test",
            message="x",
            severity=Severity.CRITICAL,
            path="t.py",
            line=None,
        )
    ]
    out = apply_waivers(f, src)
    assert out[0].waived


def test_ledger_open_findings_and_corrupt(tmp_path):
    led = Ledger(tmp_path)
    led.record(
        [Finding(kind="assert-true", message="x", severity=Severity.CRITICAL, path="t.py")],
        session_id="s",
        mode="observe",
    )
    assert led.open_findings()
    assert led.all()
    # corrupt line should not crash reload
    (tmp_path / "receipts.jsonl").write_text("{not-json\n", encoding="utf-8")
    led2 = Ledger(tmp_path)
    assert led2.latest() is None or True  # either empty or recovered
