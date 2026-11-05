from proveit_tests.detectors.paths import is_ci_path, is_test_path
from proveit_tests.detectors.waivers import extract_waivers
from proveit_tests.findings import Finding, Severity
from proveit_tests.detectors.waivers import apply_waivers


def test_test_paths():
    assert is_test_path("tests/test_foo.py")
    assert is_test_path("src/foo_test.py")
    assert is_test_path("app.test.ts")
    assert not is_test_path("src/main.py")


def test_ci_paths():
    assert is_ci_path(".github/workflows/ci.yml")
    assert is_ci_path(".gitlab-ci.yml")


def test_waiver_extract():
    src = "assert True  # proveit: intended demo fixture\n"
    w = extract_waivers(src)
    assert 1 in w
    assert "demo" in w[1]


def test_apply_waivers():
    src = "assert True  # proveit: intended ok\n"
    f = [Finding(kind="assert-true", message="t", severity=Severity.CRITICAL, path="t.py", line=1)]
    out = apply_waivers(f, src)
    assert out[0].waived
