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
