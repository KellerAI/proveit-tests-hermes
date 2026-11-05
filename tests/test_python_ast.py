from __future__ import annotations

from pathlib import Path

from proveit_tests.detectors.python_ast import detect_python_diff, detect_python_source

CORPUS = Path(__file__).resolve().parents[1] / "corpus"


def _read(name: str) -> str:
    return (CORPUS / name).read_text(encoding="utf-8")


def test_assert_true():
    f = detect_python_source(_read("cheats/assert_true.py"), path="test_x.py")
    assert any(x.kind == "assert-true" and not x.waived for x in f)


def test_skip():
    f = detect_python_source(_read("cheats/skip_test.py"), path="test_x.py")
    assert any(x.kind == "skip-or-xfail" and not x.waived for x in f)


def test_xfail():
    f = detect_python_source(_read("cheats/xfail_test.py"), path="test_x.py")
    assert any(x.kind == "skip-or-xfail" and not x.waived for x in f)


def test_try_except_pass():
    f = detect_python_source(_read("cheats/try_except_pass.py"), path="test_x.py")
    assert any(x.kind == "try-except-pass" and not x.waived for x in f)


def test_tautology():
    f = detect_python_source(_read("cheats/tautology.py"), path="test_x.py")
    assert any(x.kind == "tautology" and not x.waived for x in f)


def test_expected_literal_rewrite():
    f = detect_python_diff(
        _read("cheats/expected_rewrite_old.py"),
        _read("cheats/expected_rewrite_new.py"),
        path="test_total.py",
    )
    assert any(x.kind == "expected-literal-rewrite" and not x.waived for x in f)


def test_removed_assert():
    f = detect_python_diff(
        _read("cheats/removed_assert_old.py"),
        _read("cheats/removed_assert_new.py"),
        path="test_total.py",
    )
    assert any(x.kind == "removed-assert" and not x.waived for x in f)


def test_deleted_test():
    f = detect_python_diff(
        _read("cheats/deleted_test_old.py"),
        _read("cheats/deleted_test_new.py"),
        path="test_suite.py",
    )
    assert any(x.kind == "deleted-test" and "test_b" in x.message for x in f)


def test_legit_rename_helper_no_critical_open():
    f = detect_python_diff(
        _read("legit/rename_helper_old.py"),
        _read("legit/rename_helper_new.py"),
        path="test_total.py",
    )
    open_critical = [x for x in f if not x.waived and x.kind in {
        "removed-assert", "deleted-test", "expected-literal-rewrite",
        "assert-true", "tautology", "skip-or-xfail", "try-except-pass",
    }]
    assert open_critical == []


def test_legit_move_assert():
    f = detect_python_diff(
        _read("legit/move_assert_old.py"),
        _read("legit/move_assert_new.py"),
        path="test_total.py",
    )
    assert not any(x.kind == "removed-assert" and not x.waived for x in f)


def test_legit_add_test():
    f = detect_python_diff(
        _read("legit/add_test_old.py"),
        _read("legit/add_test_new.py"),
        path="test_suite.py",
    )
    assert not any(x.kind == "deleted-test" for x in f)


def test_waiver_marks_skip():
    f = detect_python_source(_read("legit/waiver_skip.py"), path="test_flaky.py")
    skips = [x for x in f if x.kind == "skip-or-xfail"]
    assert skips
    assert all(x.waived for x in skips)
    assert skips[0].waiver_reason


def test_stronger_assert_ok():
    f = detect_python_diff(
        _read("legit/stronger_assert_old.py"),
        _read("legit/stronger_assert_new.py"),
        path="test_total.py",
    )
    assert not any(x.kind == "removed-assert" for x in f)


# --- Net-new semantics (Andrej breaker P0, 2026-11-05) ----------------------

_PRE_SKIP = (
    "import pytest\n\n"
    "@pytest.mark.skip(reason='flaky upstream')\n"
    "def test_old():\n    assert 1 == 1\n\n"
    "def test_b():\n    assert 2 == 2\n"
)


def test_identical_old_new_with_preexisting_skip_not_flagged():
    assert [f for f in detect_python_diff(_PRE_SKIP, _PRE_SKIP, path="test_x.py") if not f.waived] == []


def test_unrelated_edit_keeps_preexisting_skip_unflagged():
    new = _PRE_SKIP.replace("def test_b():\n    assert 2 == 2\n", "def test_b():\n    assert 2 == 2\n    assert add(1, 2) == 3\n")
    new = "# header comment\n" + new  # shifts every line number
    assert [f.kind for f in detect_python_diff(_PRE_SKIP, new, path="test_x.py")] == []


def test_newly_added_skip_is_flagged():
    new = _PRE_SKIP.replace("def test_b():", "@pytest.mark.skip\ndef test_b():")
    kinds = [f.kind for f in detect_python_diff(_PRE_SKIP, new, path="test_x.py")]
    assert kinds.count("skip-or-xfail") == 1


def test_preexisting_assert_true_and_tautology_not_flagged_but_new_one_is():
    old = "def test_a():\n    assert True\n\ndef test_b():\n    x = 1\n    assert x == x\n"
    assert detect_python_diff(old, old, path="test_x.py") == []
    new = old + "\ndef test_c():\n    assert True\n"
    kinds = [f.kind for f in detect_python_diff(old, new, path="test_x.py")]
    assert kinds == ["assert-true"]


def test_new_file_everything_is_new():
    kinds = {f.kind for f in detect_python_diff("", _PRE_SKIP, path="test_x.py")}
    assert "skip-or-xfail" in kinds
