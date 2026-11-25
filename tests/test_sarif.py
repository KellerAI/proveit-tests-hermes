import hashlib
import json

import pytest

from test_ci import change_test, cli
from test_ship_gate import repo


@pytest.mark.parametrize(("replacement", "code", "verdict", "rule", "level"), [
    (None, 0, "PASS", None, None),
    ("total() == 5", 0, "WARN", "expected-value-changed", "warning"),
    ("True", 1, "BLOCK", "assert-true", "error"),
])
def test_ci_sarif_output(repo, replacement, code, verdict, rule, level):
    if replacement:
        change_test(repo, replacement)
    base = "HEAD^" if replacement else "HEAD"
    result = cli(repo, base, "--format", "sarif")
    assert result.returncode == code
    sarif = json.loads(result.stdout)
    assert sarif["version"] == "2.1.0"
    assert sarif["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
    assert len(sarif["runs"]) == 1
    run = sarif["runs"][0]
    assert run["properties"]["verdict"] == verdict
    assert run["invocations"] == [{"executionSuccessful": True}]
    driver = run["tool"]["driver"]
    assert driver["name"] == "ProveIt Tests"

    if rule is None:
        assert driver["rules"] == []
        assert run["results"] == []
        return

    assert [r["id"] for r in driver["rules"]] == [rule]
    item, = run["results"]
    assert item["ruleId"] == rule
    assert item["level"] == level
    assert item["locations"] == [{
        "physicalLocation": {
            "artifactLocation": {"uri": "test_total space.py"},
            "region": {"startLine": 2},
        }
    }]
    expected_key = f"test_total space.py:2:{rule}:{item['message']['text']}"
    expected_id = hashlib.sha256(expected_key.encode()).hexdigest()[:16]
    assert item["partialFingerprints"] == {"proveitFindingId/v1": expected_id}
    assert item["properties"]["id"] == expected_id
    assert item["properties"]["tier"] == ("block" if code else "review")


def test_ci_sarif_warn_mode_downgrades_level(repo):
    change_test(repo, "True")
    result = cli(repo, "HEAD^", "--format", "sarif", "--mode", "warn")
    assert result.returncode == 0
    sarif = json.loads(result.stdout)
    run = sarif["runs"][0]
    assert run["properties"]["verdict"] == "WARN"
    assert run["results"][0]["level"] == "warning"


def test_ci_sarif_inspection_failure(repo):
    result = cli(repo, "missing", "--format", "sarif")
    assert result.returncode == 2
    sarif = json.loads(result.stdout)
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["properties"]["verdict"] == "BLOCK"
    assert run["results"] == []
    inv, = run["invocations"]
    assert inv["executionSuccessful"] is False
    assert "could not inspect" in inv["toolExecutionNotifications"][0]["message"]["text"]
