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


@pytest.mark.parametrize("case", ["approx", "named", "list", "negative", "unittest"])
@pytest.mark.parametrize(("stem", "kind", "tier"), [
    ("renamed_expectation", "renamed-test-changed-expectation", "block"),
    ("expected_rewrite", "expected-value-changed", "review"),
])
def test_expectation_expression_rewrite(case, stem, kind, tier):
    old = CORPUS / "cheats" / f"{stem}_{case}_old.py"
    assert [(f.kind, f.tier) for f in findings(old)] == [(kind, tier)]


@pytest.mark.parametrize("case", ["rename_unittest", "correct_actual_operand"])
def test_unchanged_unittest_expectation(case):
    assert findings(CORPUS / "legit" / f"{case}_old.py") == []


def test_rewrite_with_added_and_reordered_checks():
    old = "def test_total():\n    assert total() < LIMIT\n    assert items() == ['a']\n"
    new = (
        "def test_total():\n    assert items() == ['a', 'b']\n"
        "    assert ready()\n    assert total() < max_total()\n"
    )
    assert {(f.kind, f.tier, f.line) for f in detect_python_diff(old, new)} == {
        ("expected-value-changed", "review", 2),
        ("expected-value-changed", "review", 4),
    }
