from proveit_tests.hooks.cron import FlagCronProbe
from proveit_tests.hooks.runtime import ProveItRuntime
from proveit_tests.modes import Mode


def test_observe_appends_warning(tmp_path):
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path)
    directive = rt.on_pre_tool_call(
        "write_file",
        args={"path": str(tmp_path / "test_x.py"), "content": "def test_a():\n    assert True\n"},
    )
    assert directive is None
    out = rt.on_transform_tool_result(result="ok")
    assert out is not None
    assert "ProveIt" in out
    assert "assert-true" in out or "weakening" in out.lower() or "Tautological" in out or "assert True" in out


def test_escalate_returns_approve(tmp_path):
    # Seed an existing good file, then propose a weakening via content arg
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.ESCALATE, ledger_dir=tmp_path)
    directive = rt.on_pre_tool_call(
        "write_file",
        args={"path": str(path), "content": "def test_a():\n    assert True\n"},
    )
    assert directive is not None
    assert directive["action"] == "approve"


def test_unattended_blocks(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    rt = ProveItRuntime(
        mode=Mode.BLOCK_UNATTENDED,
        ledger_dir=tmp_path,
        cron=FlagCronProbe(True),
    )
    directive = rt.on_pre_tool_call(
        "write_file",
        args={"path": str(path), "content": "def test_a():\n    assert True\n"},
    )
    assert directive is not None
    assert directive["action"] == "block"


def test_command_pytest_or_true_escalate(tmp_path):
    rt = ProveItRuntime(mode=Mode.ESCALATE, ledger_dir=tmp_path)
    directive = rt.on_pre_tool_call("terminal", args={"command": "pytest || true"})
    assert directive is not None
    assert directive["action"] == "approve"


def test_pre_verify_one_shot(tmp_path):
    path = tmp_path / "test_x.py"
    path.write_text("def test_a():\n    assert 1 == 1\n", encoding="utf-8")
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path)
    rt.on_pre_tool_call(
        "write_file",
        args={"path": str(path), "content": "def test_a():\n    assert True\n"},
    )
    d1 = rt.on_pre_verify(changed_paths=[str(path)], attempt=0)
    assert d1 is not None
    assert d1.get("action") == "continue"
    d2 = rt.on_pre_verify(changed_paths=[str(path)], attempt=0)
    assert d2 is None  # one-shot


def test_slash_proveit(tmp_path):
    rt = ProveItRuntime(mode=Mode.OBSERVE, ledger_dir=tmp_path)
    assert "empty" in rt.slash_proveit().lower() or "ProveIt" in rt.slash_proveit()
