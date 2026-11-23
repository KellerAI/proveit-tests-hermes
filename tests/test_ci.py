import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from test_ship_gate import TEST, git, repo

ROOT = Path(__file__).resolve().parents[1]


def cli(repo, base, *args):
    return subprocess.run(
        [sys.executable, "-m", "proveit_tests.ci", "--repo", str(repo), "--base", base, *args],
        cwd=ROOT, capture_output=True, text=True,
    )


def change_test(repo, replacement):
    path = repo / "test_total space.py"
    path.write_text(TEST.replace("total() == 4", replacement), encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "test edit")


@pytest.mark.parametrize(("replacement", "code", "verdict", "rule"), [
    (None, 0, "PASS", None),
    ("total() == 5", 0, "WARN", "expected-value-changed"),
    ("True", 1, "BLOCK", "assert-true"),
])
def test_ci_exit_and_json(repo, replacement, code, verdict, rule):
    if replacement:
        change_test(repo, replacement)
    base = "HEAD^" if replacement else "HEAD"
    result = cli(repo, base, "--format", "json")
    assert result.returncode == code
    output = json.loads(result.stdout)
    assert output["verdict"] == verdict
    if rule is None:
        assert output["findings"] == []
    else:
        finding, = output["findings"]
        assert finding == {
            "id": finding["id"], "rule": rule, "file": "test_total space.py", "line": 2,
            "severity": verdict, "detail": finding["detail"],
            "tier": "block" if code else "review",
        }
        text = "{file}:{line}:{rule}:{detail}".format(**finding)
        assert finding["id"] == hashlib.sha256(text.encode()).hexdigest()[:16]
        assert cli(repo, base, "--format", "json").stdout == result.stdout


def test_ci_inspection_failure(repo):
    result = cli(repo, "missing", "--mode", "warn", "--format", "json")
    assert result.returncode == 2
    assert json.loads(result.stdout)["verdict"] == "BLOCK"
    assert "could not inspect" in json.loads(result.stdout)["error"]


@pytest.mark.parametrize(("replacement", "level", "rule"), [
    ("total() == 5", "warning", "expected-value-changed"),
    ("True", "error", "assert-true"),
])
def test_ci_github_annotation(repo, replacement, level, rule):
    change_test(repo, replacement)
    result = cli(repo, "HEAD^", "--format", "github")
    assert result.stdout.startswith(f"::{level} file=test_total space.py,line=2,title={rule}::")
    if level == "error":
        warn = cli(repo, "HEAD^", "--format", "github", "--mode", "warn")
        assert warn.returncode == 0
        assert warn.stdout.startswith("::warning ")


def test_workflow_checks_all_platforms_and_uses_base_detector():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'os: [ubuntu-latest, macos-latest, windows-latest]' in workflow
    assert 'python: ["3.11", "3.13"]' in workflow
    assert 'git worktree add --detach ../base "origin/$BASE"' in workflow
    assert "cd ../base" in workflow
    assert '--repo "$GITHUB_WORKSPACE"' in workflow
