"""Adversarial corpus: cheats must flag; legit refactors must stay quiet."""

from __future__ import annotations

from pathlib import Path

from proveit_tests.detectors.commands import detect_ci_diff, detect_command_weakenings
from proveit_tests.detectors.js_ts import detect_js_ts_diff, detect_js_ts_source
from proveit_tests.detectors.python_ast import detect_python_diff, detect_python_source

CORPUS = Path(__file__).resolve().parents[1] / "corpus"

CRITICAL = {
    "removed-assert",
    "deleted-test",
    "expected-literal-rewrite",
    "assert-true",
    "tautology",
    "skip-or-xfail",
    "try-except-pass",
    "assertionless-test",
    "syntax-error-in-test",
    "js-skip",
    "js-only",
    "js-expect-true",
    "js-assert-true",
    "js-empty-catch",
    "js-deleted-test",
    "js-removed-expect",
    "js-expected-literal-rewrite",
    "ci-continue-on-error",
    "ci-allow-failure",
    "ci-soft-fail",
    "pytest-or-true",
    "pytest-k-not",
    "pytest-deselect",
    "pass-with-no-tests",
    "force-exit-zero",
    "ignore-test-failure",
}


def _read(rel: str) -> str:
    return (CORPUS / rel).read_text(encoding="utf-8")


def _open_critical(findings):
    return [f for f in findings if not f.waived and f.kind in CRITICAL]


def test_cheat_assertionless():
    f = detect_python_source(_read("cheats/assertionless.py"), path="test_x.py")
    assert any(x.kind == "assertionless-test" and not x.waived for x in f)


def test_cheat_unittest_skip():
    f = detect_python_source(_read("cheats/unittest_skip.py"), path="test_x.py")
    assert any(x.kind == "skip-or-xfail" and not x.waived for x in f)


def test_cheat_syntax_break():
    f = detect_python_diff(
        _read("cheats/syntax_break_old.py"),
        _read("cheats/syntax_break_new.py"),
        path="test_x.py",
    )
    assert any(x.kind == "syntax-error-in-test" for x in f)


def test_cheat_js_only():
    f = detect_js_ts_source(_read("cheats/js_only.test.js"), path="x.test.js")
    assert any(x.kind == "js-only" for x in f)


def test_cheat_js_empty_catch():
    f = detect_js_ts_source(_read("cheats/js_empty_catch.test.js"), path="x.test.js")
    assert any(x.kind == "js-empty-catch" for x in f)


def test_cheat_deselect_script():
    f = detect_command_weakenings(_read("cheats/pytest_deselect.sh").strip())
    assert any(x.kind == "pytest-deselect" for x in f)


def test_legit_extract_helper_no_fp():
    f = detect_python_diff(
        _read("legit/extract_helper_old.py"),
        _read("legit/extract_helper_new.py"),
        path="test_total.py",
    )
    assert _open_critical(f) == []


def test_legit_rename_test_no_fp():
    f = detect_python_diff(
        _read("legit/rename_test_old.py"),
        _read("legit/rename_test_new.py"),
        path="test_total.py",
    )
    assert not any(x.kind == "deleted-test" and not x.waived for x in f)


def test_legit_reformat_no_fp():
    f = detect_python_diff(
        _read("legit/reformat_old.py"),
        _read("legit/reformat_new.py"),
        path="test_total.py",
    )
    assert _open_critical(f) == []


def test_legit_type_hints_no_fp():
    f = detect_python_diff(
        _read("legit/type_hints_old.py"),
        _read("legit/type_hints_new.py"),
        path="test_total.py",
    )
    assert _open_critical(f) == []


def test_waiver_assert_true():
    f = detect_python_source(_read("legit/waiver_assert_true.py"), path="test_smoke.py")
    truths = [x for x in f if x.kind == "assert-true"]
    assert truths
    assert all(x.waived for x in truths)


def test_every_cheat_file_flags_something():
    """Smoke: each cheats/*.py|*.js|*.yml|*.sh produces ≥1 open critical finding."""
    cheats = CORPUS / "cheats"
    for path in sorted(cheats.iterdir()):
        if path.name.endswith(("_old.py", "_old.js")):
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            old = cheats / path.name.replace("_new.py", "_old.py")
            if path.name.endswith("_new.py") and old.exists():
                findings = detect_python_diff(old.read_text(), text, path=path.name)
            else:
                findings = detect_python_source(text, path=path.name)
        elif path.suffix in {".js", ".ts", ".tsx"}:
            findings = detect_js_ts_source(text, path=path.name)
        elif path.suffix in {".yml", ".yaml"}:
            findings = detect_ci_diff("", text, path=path.name)
        elif path.suffix == ".sh":
            findings = detect_command_weakenings(text.strip())
        else:
            continue
        open_f = [f for f in findings if not f.waived]
        assert open_f, f"cheat {path.name} produced no open findings"
