import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import pytest

from proveit_tests.hooks.cron import FlagCronProbe
from proveit_tests.hooks.runtime import ProveItRuntime

TEST = "def test_total():\n    assert total() == 4\n"


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        text=True,
        env={key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
    ).strip()


@pytest.fixture
def repo():
    with TemporaryDirectory(prefix="proveit git ") as directory:
        root = Path(directory)
        git(root, "init", "-q", "-b", "main")
        (root / "test_total space.py").write_bytes(TEST.encode())
        (root / "src.py").write_text("def total(): return 3\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "baseline")
        yield root


def run(rt, repo, command):
    return rt.on_pre_tool_call("terminal", {"command": command, "workdir": str(repo)})


@pytest.mark.parametrize(("change", "rule"), [
    ("import pytest\n@pytest.mark.skip\n" + TEST, "skip-or-xfail"),
    (None, "deleted-test-file"),
    (TEST.replace("total() == 4", "True"), "assert-true"),
])
def test_staged_commit_blocks(repo, change, rule):
    path = repo / "test_total space.py"
    if change is None:
        path.unlink()
    else:
        path.write_text(change, encoding="utf-8")
    git(repo, "add", "-A")
    rt = ProveItRuntime()
    result = run(rt, repo, 'git commit --amend -m "test"')
    assert result["action"] == "block"
    assert rule in result["message"]
    assert rt.ledger.latest().meta == {
        "verdict": "BLOCK", "ship_point": "commit",
        "head_sha": git(repo, "rev-parse", "HEAD"), "base_sha": git(repo, "rev-parse", "HEAD"),
    }


def test_clean_commit_and_git_c_with_spaces(repo):
    (repo / "src.py").write_text("def total(): return 4\n", encoding="utf-8")
    git(repo, "add", "src.py")
    rt = ProveItRuntime()
    assert rt.on_pre_tool_call("terminal", {"command": f'FLAG=yes git -C "{repo}" commit -m fix'}) is None
    assert rt.ledger.latest().meta["verdict"] == "CLEAN"


def test_commit_all_uses_tracked_worktree_and_cd_prefix(repo):
    (repo / "test_total space.py").write_bytes(TEST.replace("total() == 4", "True").replace("\n", "\r\n").encode())
    rt = ProveItRuntime()
    assert run(rt, repo, "git commit -m staged") is None
    result = rt.on_pre_tool_call("terminal", {"command": f'cd "{repo}" && git commit -am tracked; echo done'})
    assert result["action"] == "block"
    assert "assert-true" in result["message"]


@pytest.mark.parametrize("unattended", [False, True])
def test_expected_value_review(repo, unattended):
    (repo / "test_total space.py").write_text(TEST.replace("== 4", "== 5"), encoding="utf-8")
    git(repo, "add", ".")
    rt = ProveItRuntime(cron=FlagCronProbe(unattended))
    result = run(rt, repo, "git commit")
    assert result["action"] == ("block" if unattended else "approve")
    assert result["rule_key"] == "proveit-tests:test-weakening"
    assert "expected-value-changed" in result["message"]


def test_new_waiver_requires_review(repo):
    (repo / "test_total space.py").write_text(
        TEST.replace("assert total() == 4", "assert True  # proveit: intended temporary exception"),
        encoding="utf-8",
    )
    git(repo, "add", ".")
    rt = ProveItRuntime()
    assert run(rt, repo, "git commit")["action"] == "approve"
    finding, = rt.ledger.latest().findings
    assert (finding["tier"], finding["waived"]) == ("review", False)


def test_existing_waiver_still_applies(repo):
    path = repo / "test_total space.py"
    original = TEST + "    # proveit: intended approved test exception\n    assert total() > 0\n"
    path.write_text(original, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "waiver")
    path.write_text(original.replace("assert total() > 0", "assert True"), encoding="utf-8")
    git(repo, "add", ".")
    rt = ProveItRuntime()
    assert run(rt, repo, "git commit") is None
    assert rt.ledger.latest().findings[0]["waived"]


def test_push_and_pr_create_use_local_refs(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "config", "remote.origin.url", "unused-local-repo")
    git(repo, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
    git(repo, "update-ref", "refs/remotes/origin/main", base)
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    git(repo, "checkout", "-qb", "feature")
    (repo / "test_total space.py").write_text(TEST.replace("total() == 4", "True"), encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "weaken")
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/feature", head)
    git(repo, "branch", "--set-upstream-to=origin/feature")
    rt = ProveItRuntime()
    assert run(rt, repo, "git push") is None
    assert rt.ledger.latest().meta["base_sha"] == head
    for command in ("gh pr create", "gh pr create -B main"):
        assert run(rt, repo, command)["action"] == "block"
        assert rt.ledger.latest().meta["base_sha"] == base
    git(repo, "branch", "--unset-upstream")
    assert run(rt, repo, "git push")["action"] == "block"
    assert rt.ledger.latest().meta["base_sha"] == base


def test_merge_requires_human_approval(repo):
    assert run(ProveItRuntime(), repo, "gh pr merge --squash")["action"] == "approve"
    assert run(ProveItRuntime(cron=FlagCronProbe(True)), repo, "gh pr merge")["action"] == "block"


def test_unknown_repo_fails_closed_but_warn_is_advisory(repo):
    missing = repo / "does not exist"
    block = run(ProveItRuntime(), missing, "git commit")
    assert block["action"] == "block"
    assert "workdir" in block["message"]
    advisory = ProveItRuntime(mode="warn")
    assert run(advisory, missing, "git commit") is None
    assert "workdir" in advisory.on_transform_tool_result(result="output")


def test_renaming_tests_out_of_watch_paths_blocks(repo):
    git(repo, "mv", "test_total space.py", "retired.py")
    rt = ProveItRuntime()
    result = run(rt, repo, "git commit")
    assert result["action"] == "block"
    assert "deleted-test-file @ test_total space.py" in result["message"]


def test_ship_gate_checks_embedded_ci_commands(repo):
    workflow = repo / ".github" / "workflows" / "checks.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs:\n  tests:\n    steps:\n      - run: pytest || true\n", encoding="utf-8")
    git(repo, "add", ".")
    result = run(ProveItRuntime(), repo, "git commit")
    assert result["action"] == "block"
    assert "pytest-or-true" in result["message"]


def test_chained_index_mutation_fails_closed(repo):
    rt = ProveItRuntime()
    result = run(rt, repo, "git add -A && git commit -m all")
    assert result["action"] == "block"
    assert "Run the ship command separately" in result["message"]
