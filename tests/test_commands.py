from proveit_tests.detectors.commands import detect_ci_diff, detect_command_weakenings


def test_pytest_or_true():
    f = detect_command_weakenings("pytest tests/ || true")
    assert any(x.kind == "pytest-or-true" for x in f)


def test_pytest_k_not():
    f = detect_command_weakenings('pytest -k "not test_billing"')
    assert any(x.kind == "pytest-k-not" for x in f)


def test_deselect():
    f = detect_command_weakenings("pytest --deselect tests/test_x.py::test_a")
    assert any(x.kind == "pytest-deselect" for x in f)


def test_pass_with_no_tests():
    f = detect_command_weakenings("pytest --passWithNoTests")
    assert any(x.kind == "pass-with-no-tests" for x in f)


def test_jest_pass_with_no_tests():
    f = detect_command_weakenings("npx jest --passWithNoTests")
    assert any(x.kind == "pass-with-no-tests" for x in f)


def test_clean_pytest_ok():
    f = detect_command_weakenings("pytest tests/ -q")
    assert f == []


def test_ci_continue_on_error_added():
    old = "jobs:\n  test:\n    steps:\n      - run: pytest\n"
    new = (
        "jobs:\n  test:\n    steps:\n      - run: pytest\n"
        "        continue-on-error: true\n"
    )
    f = detect_ci_diff(old, new, path=".github/workflows/ci.yml")
    assert any(x.kind == "ci-continue-on-error" for x in f)


def test_ci_continue_already_present_not_reflagged():
    body = (
        "jobs:\n  test:\n    steps:\n      - run: pytest\n"
        "        continue-on-error: true\n"
    )
    f = detect_ci_diff(body, body, path=".github/workflows/ci.yml")
    assert f == []
