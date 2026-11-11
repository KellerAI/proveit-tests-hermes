"""Regressions for Sachin's independent fast pass against 2412a18 (three bugs)."""

from __future__ import annotations

import json

from proveit_tests.hooks.runtime import ProveItRuntime
from proveit_tests.modes import Mode

ORIG = "def test_a():\n    assert add(1, 1) == 2\n"
WEAK = "def test_a():\n    assert True\n"
WAIVED = "def test_a():\n    assert True  # proveit: intended demo fixture\n"


def _write(rt, path, content):
    """Simulate a write_file tool call end to end (pre, disk write, post)."""
    args = {"path": str(path), "content": content}
    d = rt.on_pre_tool_call("write_file", args=args)
    path.write_text(content, encoding="utf-8")
    rt.on_post_tool_call("write_file", args=args, result="ok")
    return d


def test_bug1_fully_waived_batch_is_logged_not_silent(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text(ORIG, encoding="utf-8")
    ledger_dir = tmp_path / "ledger"
    rt = ProveItRuntime(mode=Mode.ESCALATE, ledger_dir=ledger_dir)

    d = _write(rt, path, WAIVED)

    assert d is None  # waived: no escalation
    assert rt._pending_warnings == []  # waived: no warning
    receipts = rt.ledger.all()
    assert len(receipts) == 1
    r = receipts[0]
    assert (r.open_count, r.waived_count) == (0, 1)
    assert r.findings[0]["waiver_reason"] == "demo fixture"
    on_disk = [json.loads(x) for x in (ledger_dir / "receipts.jsonl").read_text().splitlines()]
    assert len(on_disk) == 1 and on_disk[0]["waived_count"] == 1
    assert rt._unexplained == []


def test_bug2_exact_restoration_clears_current_warning_keeps_history(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text(ORIG, encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path / "ledger")

    _write(rt, path, WEAK)
    assert len(rt._unexplained) == 1
    _write(rt, path, ORIG)  # original bytes restored

    assert rt._unexplained == []
    assert rt.on_pre_verify(changed_paths=[str(path)]) is None
    assert rt.footer_line().startswith("0 open weakening(s)")
    assert len(rt.ledger.all()) == 1  # historical receipt kept
    assert rt.ledger.all()[0].open_count == 1


def test_bug2_unrelated_later_edit_does_not_clear_weakening(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text(ORIG, encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path / "ledger")

    _write(rt, path, WEAK)
    _write(rt, path, "# unrelated comment\n" + WEAK)

    assert len(rt._unexplained) == 1
    nudge = rt.on_pre_verify(changed_paths=[str(path)])
    assert nudge and "unexplained weakening remains" in nudge["message"]


def test_bug3_open_count_spans_files_and_drops_on_restore(tmp_path):
    a = tmp_path / "test_a.py"
    b = tmp_path / "test_b.py"
    a.write_text(ORIG, encoding="utf-8")
    b.write_text(ORIG, encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path / "ledger")

    _write(rt, a, WEAK)
    _write(rt, b, WEAK)
    assert len(rt._unexplained) == 2
    assert rt.footer_line().startswith("2 open weakening(s)")

    _write(rt, a, ORIG)
    assert len(rt._unexplained) == 1
    assert rt._unexplained[0].path == str(b)
    assert rt.footer_line().startswith("1 open weakening(s)")


import pytest


@pytest.mark.parametrize("mode", [Mode.OBSERVE, Mode.ESCALATE])
def test_failed_restore_does_not_clear_weakening(tmp_path, mode):
    """Andrej's break on b5d77a3: a restore whose write fails must leave 1 open."""
    path = tmp_path / "test_x.py"
    path.write_text(ORIG, encoding="utf-8")
    rt = ProveItRuntime(mode=mode, ledger_dir=tmp_path / "ledger")

    _write(rt, path, WEAK)
    assert len(rt._unexplained) == 1

    # Try to restore the original bytes, but the write never lands.
    args = {"path": str(path), "content": ORIG}
    rt.on_pre_tool_call("write_file", args=args)
    rt.on_post_tool_call("write_file", args=args, result="Error: permission denied")

    assert path.read_text(encoding="utf-8") == WEAK
    assert len(rt._unexplained) == 1
    assert rt.on_pre_verify(changed_paths=[str(path)]) is not None
    assert rt.footer_line().startswith("1 open weakening(s)")


def test_successful_restore_after_failed_restore_still_clears(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text(ORIG, encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path / "ledger")

    _write(rt, path, WEAK)
    args = {"path": str(path), "content": ORIG}
    rt.on_pre_tool_call("write_file", args=args)
    rt.on_post_tool_call("write_file", args=args, result="Error: permission denied")
    assert len(rt._unexplained) == 1

    _write(rt, path, ORIG)
    assert rt._unexplained == []


def test_denied_escalation_does_not_stay_open(tmp_path):
    """A weakening the human denies never lands, so it must not count as open.

    Hermes v0.23.0 still emits post_tool_call for a blocked call
    (model_tools: ``_emit(result, status="blocked", ...)``).
    """
    path = tmp_path / "test_x.py"
    path.write_text(ORIG, encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.ESCALATE, ledger_dir=tmp_path / "ledger")

    args = {"path": str(path), "content": WEAK}
    d = rt.on_pre_tool_call("write_file", args=args)
    assert d is not None and d["action"] == "approve"
    rt.on_post_tool_call("write_file", args=args, result="Error: denied by user", status="blocked")

    assert path.read_text(encoding="utf-8") == ORIG
    assert rt._unexplained == []
    assert len(rt.ledger.all()) == 1  # the attempt is still on the record
