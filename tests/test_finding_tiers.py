from pathlib import Path

import pytest

from proveit_tests.detectors.python_ast import detect_python_diff

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
LEGIT = sorted((CORPUS / "legit" / "wrongtest").glob("*_old.py"))


def findings(old):
    new = old.with_name(old.name.replace("_old.py", "_new.py"))
    return detect_python_diff(old.read_text(encoding="utf-8"), new.read_text(encoding="utf-8"))


@pytest.mark.parametrize("old", LEGIT, ids=lambda path: path.stem)
def test_legitimate_expected_value_fix(old):
    assert [(f.kind, f.tier) for f in findings(old)] == [("expected-value-changed", "review")]


@pytest.mark.parametrize(("case", "kind"), [
    ("renamed_expectation", "renamed-test-changed-expectation"),
    ("weaker_membership", "assertion-weakened"),
    ("broad_exception", "assertion-weakened"),
    ("widened_exception", "assertion-weakened"),
])
def test_weakening_tier(case, kind):
    assert [(f.kind, f.tier) for f in findings(CORPUS / "cheats" / f"{case}_old.py")] == [
        (kind, "block")
    ]
